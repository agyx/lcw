#!/usr/bin/env python3

import json
import sys
import subprocess
import os
import munch
import time
from optparse import OptionParser

SATS_PER_BTC = 100000000
CLI_LIGHTNING_COMMAND = None
DAY = 86400
NOW = int(time.time())
LCW_DATA_PATH = os.getenv("HOME") + "/.lcwdata.json"


def file_content(path):
    try:
        file = open(path, mode="r")
        content = file.read()
        file.close()
        return json.loads(content)
    except Exception:
        return None


def cli_query(params):
    global CLI_LIGHTNING_COMMAND
    if CLI_LIGHTNING_COMMAND is None:
        CLI_LIGHTNING_COMMAND_VARNAME = "CLI_LIGHTNING_COMMAND"
        CLI_LIGHTNING_COMMAND = os.getenv(CLI_LIGHTNING_COMMAND_VARNAME)
        if not CLI_LIGHTNING_COMMAND:
            print("{} env var is not set!".format(CLI_LIGHTNING_COMMAND_VARNAME))
            exit(1)
    return json.loads(subprocess.check_output([CLI_LIGHTNING_COMMAND] + params))


def age_string(timestamp):
    global NOW
    return age_string2(NOW - timestamp)


def age_string2(age_seconds):
    age = age_seconds
    if age < DAY:
        return "   today"
    days = age // DAY
    if days == 1:
        return " 1 day  "
    else:
        return "{:2d} days ".format(days)


def peer_id_string(peer_id, verbose=False):
    if verbose:
        return peer_id
    else:
        return "{}...{}".format(
            peer_id[:8],
            peer_id[-8:],
        )


def day(days_ago=0):
    return time.strftime("%Y%m%d", time.localtime(NOW - days_ago * 86400))


def timestamp_from_day(day):
    return int(time.mktime(time.strptime(day + " 00:00:00", '%Y%m%d %H:%M:%S')))


class CLightning:

    def __init__(self, test_mode=False):
        self.test_mode = test_mode

    def getinfo(self):
        if self.test_mode:
            return file_content("tests/getinfo.txt")
        else:
            return cli_query(['getinfo'])

    def listfunds(self):
        if self.test_mode:
            return file_content("tests/listfunds.txt")
        else:
            return cli_query(['listfunds'])

    def listchannels(self, short_channel_id, source_node_id):
        if self.test_mode:
            return file_content("tests/listchannels.txt")
        else:
            return cli_query(['listchannels', short_channel_id, source_node_id])

    def listpeers(self):
        if self.test_mode:
            return file_content("tests/listpeers.txt")
        else:
            return cli_query(["listpeers"])

    def setchannelfee(self, id, base, ppm):
        if self.test_mode:
            return {}
        else:
            return cli_query(["setchannelfee", id, str(base), str(ppm)])


class Node:

    def __init__(self, since=None):
        self.data_stored = None
        self.date_ref = None
        self.since = None
        if since is not None:
            data_stored = file_content(LCW_DATA_PATH)
            if data_stored is not None:
                self.date_ref = day(since)
                if self.date_ref in data_stored:
                    self.data_stored = data_stored[self.date_ref]
                    self.period = NOW - timestamp_from_day(self.date_ref)
                    self.since = since
        self.getinfo = clapi.getinfo()
        self.id = self.getinfo["id"]
        self.fees_collected = self.getinfo["msatoshi_fees_collected"] / 1000
        self.listfunds = clapi.listfunds()
        self.listchannels = clapi.listchannels("null", self.id)
        self.listpeers = clapi.listpeers()
        self.channels = {}
        self.all_last_updates = []

        self.wallet_value_confirmed = 0
        self.wallet_value_unconfirmed = 0
        for output in self.listfunds["outputs"]:
            if output["status"] == "confirmed":
                self.wallet_value_confirmed += output["value"]
            else:
                self.wallet_value_unconfirmed += output["value"]
        self.total_wallet = self.wallet_value_confirmed + self.wallet_value_unconfirmed

        self.input_capacity = 0
        self.output_capacity = 0
        self.channel_count = 0
        self.in_payments = 0
        self.out_payments = 0
        self.new_channels = 0
        self.block_height = self.getinfo["blockheight"]
        for channel_data in self.listfunds["channels"]:
            self.channel_count += 1
            total = channel_data["channel_total_sat"]
            output = channel_data["channel_sat"]
            input = total - output
            if "short_channel_id" in channel_data:
                short_channel_id = channel_data["short_channel_id"]
                new_channel = False
            else:
                short_channel_id = "new-" + str(self.new_channels)
                self.new_channels += 1
                new_channel = True
            channel = munch.Munch(peer_id=channel_data["peer_id"],
                                  input_capacity=input,
                                  output_capacity=output,
                                  total_capacity=input + output,
                                  state=channel_data["state"],
                                  last_update=NOW,
                                  in_payments=0,
                                  out_payments=0,
                                  in_msatoshi_fulfilled=0,
                                  out_msatoshi_fulfilled=0,
                                  new_channel=new_channel,
                                  total_payments=0,
                                  base_fee_msat=0,
                                  ppm_fee=0)
            self.channels[short_channel_id] = channel
            self.input_capacity += input
            self.output_capacity += output
        self.total = self.input_capacity + self.output_capacity
        for channel_data in self.listchannels["channels"]:
            channel_id = channel_data["short_channel_id"]
            if channel_id not in self.channels:
                print("unknown channel {} in listfunds".format(channel_id))
                continue
            channel = self.channels[channel_id]
            channel.last_update = channel_data["last_update"]
            self.all_last_updates += [channel.last_update]
            channel.base_fee_msat = channel_data["base_fee_millisatoshi"]
            channel.ppm_fee = channel_data["fee_per_millionth"]
        for peer_data in self.listpeers["peers"]:
            for channel_data in peer_data["channels"]:
                if "short_channel_id" not in channel_data:
                    continue
                channel_id = channel_data["short_channel_id"]
                if channel_id not in self.channels:
                    print("unknown channel {} in listpeers".format(channel_id))
                    continue
                channel = self.channels[channel_id]
                channel.in_payments = channel_data["in_payments_fulfilled"]
                channel.out_payments = channel_data["out_payments_fulfilled"]
                channel.in_msatoshi_fulfilled = channel_data["in_msatoshi_fulfilled"]
                channel.out_msatoshi_fulfilled = channel_data["out_msatoshi_fulfilled"]
                channel_ref = self.get_channel_ref(channel_id)
                if channel_ref is not None:
                    # print(data_stored)
                    # print("{} {} {} {}".format(channel.in_payments,
                    #                           channel.out_payments,
                    #                           channel_ref["in_payments"],
                    #                           channel_ref["out_payments"]))
                    channel.in_payments -= channel_ref["in_payments"]
                    channel.out_payments -= channel_ref["out_payments"]
                channel.total_payments = channel.in_payments + channel.out_payments
                self.in_payments += channel.in_payments
                self.out_payments += channel.out_payments

        for (channel_id, channel) in self.channels.items():
            channel_ref = self.get_channel_ref(channel_id)
            if channel.new_channel:
                channel.funding_block = self.block_height
            else:
                channel.funding_block = int(channel_id.split("x")[0])
            channel.age = (self.block_height - channel.funding_block) * 600
            if channel_ref is not None:
                period = self.period
            else:
                period = channel.age
            if period <= 0:
                channel.tx_per_day = 0
            else:
                channel.tx_per_day = channel.total_payments / (period / 86400)
            if channel.output_capacity == 0:
                channel.used_capacity = 1000
            else:
                channel.used_capacity = channel.tx_per_day / channel.output_capacity * SATS_PER_BTC

    def get_channel_ref(self, channel_id):
        if self.data_stored is not None and channel_id in self.data_stored:
            return self.data_stored[channel_id]
        else:
            return None

    def set_fees(self, min_base, min_ppm, max_base, max_ppm):
        for (channel_id, channel) in self.channels.items():
            out_percent = channel.output_capacity / (channel.input_capacity + channel.output_capacity) * 100
            if channel.base_fee_msat == 0 and channel.ppm_fee == 0:
                print("{:13s} skipped".format(channel_id))
                continue
            elif out_percent <= 10:
                new_base_fee = max_base
                new_ppm_fee = max_ppm
            elif out_percent <= 40:
                new_base_fee = (7 * min_base + max_base) // 8
                new_ppm_fee = (7 * min_ppm + max_ppm) // 8
            else:
                new_base_fee = min_base
                new_ppm_fee = min_ppm
            if new_base_fee == channel.base_fee_msat and new_ppm_fee == channel.ppm_fee:
                status = "(no change)"
            else:
                clapi.setchannelfee(channel_id, new_base_fee, new_ppm_fee)
                status = "(updated)"
            print("{:13s} {:4.0f}%  {:5d}/{:5d} -> {:5d}/{:5d}  {}".format(channel_id,
                                                                           out_percent,
                                                                           channel.base_fee_msat,
                                                                           channel.ppm_fee,
                                                                           new_base_fee,
                                                                           new_ppm_fee,
                                                                           status))

    def print_status(self, verbose=False, sort_key=None):
        print("Wallet funds (BTC):")
        print("- Confirmed:   {:11.8f}".format(self.wallet_value_confirmed / SATS_PER_BTC))
        print("- Unconfirmed: {:11.8f}".format(self.wallet_value_unconfirmed / SATS_PER_BTC))
        print("- TOTAL:       {:11.8f}".format(self.total_wallet / SATS_PER_BTC))
        print("Channels: " + ("(ref: {} days ago)".format(self.since) if self.since is not None else ""))
        items = list(self.channels.items())
        if sort_key is not None:
            if sort_key.startswith("-"):
                reverse = True
                sort_key = sort_key[1:]
            else:
                reverse = False
            items.sort(key=lambda item: item[1][sort_key], reverse=reverse)
        for (channel_id, channel) in items:
            input_str = "{:11.8f}".format(
                channel.input_capacity / SATS_PER_BTC) if channel.input_capacity else " -         "
            output_str = "{:11.8f}".format(
                channel.output_capacity / SATS_PER_BTC) if channel.output_capacity else " -         "
            payments_str = "{:8s} {:4d}".format(
                "{:4d}-{:<d}".format(
                    channel.in_payments,
                    channel.out_payments),
                channel.total_payments,
            )
            print("- {:13s}  {} {}-{}  {:11.8f}  {}  {}  {:5.1f}  {:8.1f}  {} ({}/{})".format(
                channel_id,
                peer_id_string(channel.peer_id, verbose),
                input_str,
                output_str,
                channel.total_capacity / SATS_PER_BTC,
                payments_str,
                age_string2(channel.age),
                channel.tx_per_day,
                channel.used_capacity,
                # age_string(channel.last_update),
                channel.state,
                channel.base_fee_msat,
                channel.ppm_fee
            ))
        print("Node summary:")
        print("- # of channels   : {}".format(self.channel_count))
        print("- Capacity        : {:.8f} ({:.8f} + {:.8f})".format(
            self.total / SATS_PER_BTC,
            self.input_capacity / SATS_PER_BTC,
            self.output_capacity / SATS_PER_BTC))
        print("- Routed payments : {}".format(self.in_payments))
        tvl = self.output_capacity + self.total_wallet
        print("- Node Value      : {:.8f} BTC".format(tvl / SATS_PER_BTC))
        print("- Fees collected  : {:.0f} sats".format(self.fees_collected))
        # self.all_last_updates.sort()
        # if len(self.all_last_updates) > 0:
        #     median_index = len(self.all_last_updates) // 2
        #     if median_index * 2 == len(self.all_last_updates):
        #         median_value = (self.all_last_updates[median_index - 1] + self.all_last_updates[median_index]) // 2
        #     else:
        #         median_value = self.all_last_updates[median_index]
        #     print("Median last update : {:4.1f} days".format((NOW - median_value) / DAY))

    def store(self):
        stored_data = file_content(LCW_DATA_PATH)
        if stored_data is None:
            stored_json = {}
        else:
            stored_json = stored_data
        today = day()
        if today in stored_json:
            print("today's data is alresady stored")
            return
        stored_json[today] = self.channels
        file = open(LCW_DATA_PATH, "w")
        file.write(json.dumps(stored_json))
        file.close()


parser = OptionParser()

parser.add_option("-t", "--test",
                  action="store_true", dest="test_mode", default=False,
                  help="Test mode")

parser.add_option("-v", "--verbose",
                  action="store_true", dest="verbose", default=False,
                  help="Verbose")

parser.add_option("-s", "--sort",
                  action="store", type="string", dest="sort_key", default=None,
                  help="Sort channels with provided key")

parser.add_option("", "--since",
                  action="store", type="int", dest="since", default=None,
                  help="Sort channels with provided key")

parser.add_option("-f", "--fees",
                  action="store", type="string", dest="fees", default="1/10/1/1000",
                  help="Sort channels with provided key")

parser.add_option("", "--command",
                  action="store", type="string", dest="command", default="status",
                  help="store: Store current channels information into json history file"
                       "status:"
                       "setfees:"
                  )

(options, args) = parser.parse_args()

clapi = CLightning(test_mode=options.test_mode)

if options.command == "store":
    options.since = None

my_node = Node(since=options.since)

if options.command == "store":
    my_node.store()
elif options.command == "setfees":
    fees = options.fees.split("/")
    my_node.set_fees(int(fees[0]), int(fees[1]), int(fees[2]), int(fees[3]))
elif options.command == "status":
    my_node.print_status(verbose=options.verbose,
                         sort_key=options.sort_key)

"""
print(clapi.getinfo())
print(clapi.listfunds())
print(clapi.listchannels(None,None))
"""
