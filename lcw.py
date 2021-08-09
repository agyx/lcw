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


# Verbosity
#     chan      peer id
# 0   wp only   very short
# 1 * wp only   short
# 2   all       short
# 3   all       short
# 4   all       short
# 5   all       long


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
        return "   today "
    days = age // DAY
    if days == 1:
        return " 1 day   "
    elif days < 90:
        return "{:2d} days  ".format(days)
    else:
        return "{:2d} months".format((days+15) // 30)


def peer_id_string(alias, peer_id, verbosity):
    if verbosity == 5:
        return "{:24.24} {}".format(alias, peer_id)
    elif verbosity == 0:
        return "{:12.12} {}...".format(
            alias,
            peer_id[:4],
        )
    else:
        return "{:16.16} {}...{}".format(
            alias,
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

    def listnodes(self):
        if self.test_mode:
            return file_content("tests/listnodes.txt")
        else:
            return cli_query(["listnodes"])

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
        self.routed_amount = 0
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
                                  ppm_fee=0,
                                  alias="?",
                                  routed_amount=0)
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
                    channel.in_msatoshi_fulfilled -= channel_ref["in_msatoshi_fulfilled"]
                    channel.out_msatoshi_fulfilled -= channel_ref["out_msatoshi_fulfilled"]
                channel.routed_amount = (channel.in_msatoshi_fulfilled + channel.out_msatoshi_fulfilled) / 1000
                channel.routed_capacity = channel.routed_amount / channel.total_capacity
                channel.total_payments = channel.in_payments + channel.out_payments
                self.in_payments += channel.in_payments
                self.out_payments += channel.out_payments
                self.routed_amount += (channel.in_msatoshi_fulfilled + channel.out_msatoshi_fulfilled) / 2 / 1000
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
            #if channel.output_capacity == 0:
            #    channel.used_capacity = 1000
            #else:
            #    channel.used_capacity = channel.tx_per_day / channel.output_capacity * SATS_PER_BTC
        # add aliases
        self.listnodes = clapi.listnodes()["nodes"]
        self.hashed_listnodes = {}
        for node in self.listnodes:
            if "alias" in node:
                self.hashed_listnodes[node["nodeid"]] = node["alias"]
        for (channel_id, channel) in self.channels.items():
            if channel.peer_id in self.hashed_listnodes:
                channel.alias = self.hashed_listnodes[channel.peer_id]

    def get_channel_ref(self, channel_id):
        if self.data_stored is not None and channel_id in self.data_stored:
            return self.data_stored[channel_id]
        else:
            return None

    def set_fees(self, force, ppm0, ppm1, ppm2, ppm3):
        DEFAULT_BASE_FEE = 0
        for (channel_id, channel) in self.channels.items():
            out_percent = channel.output_capacity / (channel.input_capacity + channel.output_capacity) * 100
            if channel.ppm_fee == 0 and not force:
                print("{:13s} skipped".format(channel_id))
                continue
            elif out_percent <= 10:
                new_ppm_fee = ppm3
            elif out_percent <= 25:
                new_ppm_fee = ppm2
            elif out_percent <= 50:
                new_ppm_fee = ppm1
            else:
                new_ppm_fee = ppm0
            if channel.base_fee_msat == DEFAULT_BASE_FEE and new_ppm_fee == channel.ppm_fee:
                continue
            clapi.setchannelfee(channel_id, DEFAULT_BASE_FEE, new_ppm_fee)
            print("{:13s} {:4.0f}%  {:5d}/{:5d} -> {:5d}/{:5d}".format(channel_id,
                                                                       out_percent,
                                                                       channel.base_fee_msat,
                                                                       channel.ppm_fee,
                                                                       DEFAULT_BASE_FEE,
                                                                       new_ppm_fee))

    def print_status(self, verbosity=0, sort_key=None, limit=0):
        print("Wallet funds (BTC):")
        print("- Confirmed:   {:11.8f}".format(self.wallet_value_confirmed / SATS_PER_BTC))
        print("- Unconfirmed: {:11.8f}".format(self.wallet_value_unconfirmed / SATS_PER_BTC))
        print("- TOTAL:       {:11.8f}".format(self.total_wallet / SATS_PER_BTC))
        print("Channels: " + ("(ref: {} days ago)".format(self.since) if self.since is not None else ""))
        items = list(self.channels.items())
        if sort_key is not None:
            if sort_key.startswith("/"):
                reverse = True
                sort_key = sort_key[1:]
            else:
                reverse = False
            items.sort(key=lambda item: item[1][sort_key], reverse=reverse)
        count = 0
        for (channel_id, channel) in items:
            if limit > 0:
                if count >= limit:
                    break
            show = True
            if verbosity <= 1:
                if channel.total_payments == 0:
                    show = False
            if channel.state != "CHANNELD_NORMAL":
                show = True
            if show is False:
                continue
            count += 1
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
            print("- {:13s}  {} {}-{}  {:11.8f}  {}  {}  {:5.1f}  {:6.2f}  {} ({}/{})".format(
                channel_id,
                peer_id_string(channel.alias, channel.peer_id, verbosity),
                input_str,
                output_str,
                channel.total_capacity / SATS_PER_BTC,
                payments_str,
                age_string2(channel.age),
                channel.tx_per_day,
                channel.routed_capacity,
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
        print("- Routed amount   : {:.8f} BTC".format(self.routed_amount / SATS_PER_BTC))
        routed_capacity = self.routed_amount / self.total * 2
        print("- Routed capacity : {:.2f}".format(routed_capacity))
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
        print()

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

parser.add_option("-v", "--verbosity",
                  action="store", type="int", dest="verbosity", default=1,
                  help="Verbosity level: 0 to 5")

parser.add_option("-l", "--limit",
                  action="store", type="int", dest="limit", default=0,
                  help="Limit number of channels logged to provided parameter")

parser.add_option("", "--force",
                  action="store_true", dest="force", default=False,
                  help="Do not skip 0 fees settings")

parser.add_option("-s", "--sort",
                  action="store", type="string", dest="sort_key", default=None,
                  help="Sort channels with provided key")

parser.add_option("", "--since",
                  action="store", type="int", dest="since", default=None,
                  help="Payments and derived stats are counted from given # of days")

parser.add_option("-f", "--fees",
                  action="store", type="string", dest="fees", default="10/20/150/1000",
                  help="Set fees from a string <ppm0>/<ppm1>/<ppm2>/<ppm3> respectively"
                       "for quartiles 100%/50%/25%/10% of %out payments."
                       "Base fee is always 0")

parser.add_option("", "--command",
                  action="store", type="string", dest="command", default="status",
                  help="store: Store current channels information into json history file"
                       "status:"
                       "setfees:"
                  )

(options, args) = parser.parse_args()

clapi = CLightning(test_mode=options.test_mode)

if options.command != "status":
    options.since = None

my_node = Node(since=options.since)

if options.command == "store":
    my_node.store()
elif options.command == "setfees":
    fees = options.fees.split("/")
    my_node.set_fees(options.force, int(fees[0]), int(fees[1]), int(fees[2]), int(fees[3]))
elif options.command == "status":
    my_node.print_status(verbosity=options.verbosity,
                         sort_key=options.sort_key,
                         limit=options.limit)

"""
print(clapi.getinfo())
print(clapi.listfunds())
print(clapi.listchannels(None,None))
"""
