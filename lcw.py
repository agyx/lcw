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


def file_content(path):
    file = open(path, mode="r")
    content = file.read()
    file.close()
    return json.loads(content)


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
            peer_id[-9:-1],
        )


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


class Node:

    def __init__(self):
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

        self.total_input = 0
        self.total_output = 0
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
                                  input=input,
                                  output=output,
                                  total=input + output,
                                  state=channel_data["state"],
                                  last_update=NOW,
                                  in_payments=0,
                                  out_payments=0,
                                  new_channel=new_channel)
            self.channels[short_channel_id] = channel
            self.total_input += input
            self.total_output += output
        self.total = self.total_input + self.total_output
        for channel_data in self.listchannels["channels"]:
            channel_id = channel_data["short_channel_id"]
            if channel_id not in self.channels:
                print("channel {} not in listfunds".format(channel_id))
                continue
            channel = self.channels[channel_id]
            channel.last_update = channel_data["last_update"]
            self.all_last_updates += [channel.last_update]
        for peer_data in self.listpeers["peers"]:
            for channel_data in peer_data["channels"]:
                if "short_channel_id" not in channel_data:
                    continue
                channel_id = channel_data["short_channel_id"]
                if channel_id not in self.channels:
                    print("channel {} not in listpeers".format(channel_id))
                    continue
                channel = self.channels[channel_id]
                channel.in_payments = channel_data["in_payments_fulfilled"]
                channel.out_payments = channel_data["out_payments_fulfilled"]
                self.in_payments += channel.in_payments
                self.out_payments += channel.out_payments
        for (channel_id, channel) in self.channels.items():
            if channel.new_channel:
                channel.funding_block = self.block_height
            else:
                channel.funding_block = int(channel_id.split("x")[0])

    def print_status(self, verbose=False):
        print("Wallet funds (BTC):")
        print("- Confirmed:   {:11.8f}".format(self.wallet_value_confirmed / SATS_PER_BTC))
        print("- Unconfirmed: {:11.8f}".format(self.wallet_value_unconfirmed / SATS_PER_BTC))
        print("- TOTAL:       {:11.8f}".format(self.total_wallet / SATS_PER_BTC))
        print("Channels:")
        for (channel_id, channel) in self.channels.items():
            input_str = "{:11.8f}".format(channel.input / SATS_PER_BTC) if channel.input else " -         "
            output_str = "{:11.8f}".format(channel.output / SATS_PER_BTC) if channel.output else " -         "
            total_payments = channel.in_payments + channel.out_payments
            payments_str = "{:8s} {:4d}".format(
                "{:4d}-{:<d}".format(
                    channel.in_payments,
                    channel.out_payments),
                total_payments,
            )
            age = (self.block_height - channel.funding_block) * 600
            if age <= 0:
                tx_per_day = 0
            else:
                tx_per_day = total_payments / (age / 86400)
            print("- {:13s}  {} {}-{}  {:11.8f}  {}  {}  {:5.1f}  {}".format(
                channel_id,
                peer_id_string(channel.peer_id, verbose),
                input_str,
                output_str,
                channel.total / SATS_PER_BTC,
                payments_str,
                age_string2(age),
                tx_per_day,
                # age_string(channel.last_update),
                channel.state,
            ))
        print("Channels summary:")
        print("- # of channels:  {}".format(self.channel_count))
        print("- Total input:   {:11.8f}".format(self.total_input / SATS_PER_BTC))
        print("- Total output:  {:11.8f}".format(self.total_output / SATS_PER_BTC))
        print("- Grand total:   {:11.8f}".format(self.total / SATS_PER_BTC))
        tvl = self.total_output + self.total_wallet
        print("Node Value         : {:11.8f}".format(tvl / SATS_PER_BTC))
        print("In payments        : {}".format(self.in_payments))
        print("Out payments       : {}".format(self.out_payments))
        print("Total payments     : {}".format(self.in_payments + self.out_payments))
        print("Fees collected     : {:14.11f}".format(self.fees_collected / SATS_PER_BTC))
        # self.all_last_updates.sort()
        # if len(self.all_last_updates) > 0:
        #     median_index = len(self.all_last_updates) // 2
        #     if median_index * 2 == len(self.all_last_updates):
        #         median_value = (self.all_last_updates[median_index - 1] + self.all_last_updates[median_index]) // 2
        #     else:
        #         median_value = self.all_last_updates[median_index]
        #     print("Median last update : {:4.1f} days".format((NOW - median_value) / DAY))


parser = OptionParser()

parser.add_option("-t", "--test",
                  action="store_true", dest="test_mode", default=False,
                  help="Test mode")

parser.add_option("-v", "--verbose",
                  action="store_true", dest="verbose", default=False,
                  help="Verbose")

(options, args) = parser.parse_args()

clapi = CLightning(test_mode=options.test_mode)

my_node = Node()

my_node.print_status(verbose=options.verbose)


"""
print(clapi.getinfo())
print(clapi.listfunds())
print(clapi.listchannels(None,None))
"""
