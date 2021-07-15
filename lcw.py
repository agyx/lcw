#!/usr/bin/env python3

import json
import sys
import subprocess
import os
import munch
import time


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
    age = NOW - timestamp
    if age < DAY:
        return "today"
    days = age // DAY
    if days == 1:
        return "1 day"
    else:
        return "{} days".format(days)


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


command = sys.argv[1]


clapi = CLightning(test_mode=(command == "test"))


class Node:

    def __init__(self):
        self.getinfo = clapi.getinfo()
        self.id = self.getinfo["id"]
        self.fees_collected = self.getinfo["msatoshi_fees_collected"] / 1000
        self.listfunds = clapi.listfunds()
        self.listchannels = clapi.listchannels("null", self.id)
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
        for channel_data in self.listfunds["channels"]:
            self.channel_count += 1
            total = channel_data["channel_total_sat"]
            output = channel_data["channel_sat"]
            input = total - output
            short_channel_id = channel_data["short_channel_id"]
            channel = munch.Munch(peer_id=channel_data["peer_id"],
                                  input=input,
                                  output=output,
                                  total=input + output,
                                  state=channel_data["state"])
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

    def print_status(self):
        print("Wallet funds (BTC):")
        print("- Confirmed:   {:11.8f}".format(self.wallet_value_confirmed / SATS_PER_BTC))
        print("- Unconfirmed: {:11.8f}".format(self.wallet_value_unconfirmed / SATS_PER_BTC))
        print("- TOTAL:       {:11.8f}".format(self.total_wallet / SATS_PER_BTC))
        print("Channels:")
        for (channel_id, channel) in self.channels.items():
            input_str = "{:11.8f}".format(channel.input / SATS_PER_BTC) if channel.input else " -         "
            output_str = "{:11.8f}".format(channel.output / SATS_PER_BTC) if channel.output else " -         "
            print("- {:13s}  {}...{} {}-{}  {:11.8f}  {}  {}".format(
                channel_id,
                channel.peer_id[:8],
                channel.peer_id[-9:-1],
                input_str,
                output_str,
                channel.total / SATS_PER_BTC,
                channel.state,
                age_string(channel.last_update)
            ))
        print("Channels summary:")
        print("- # of channels:  {}".format(self.channel_count))
        print("- Total input:   {:11.8f}".format(self.total_input / SATS_PER_BTC))
        print("- Total output:  {:11.8f}".format(self.total_output / SATS_PER_BTC))
        print("- Grand total:   {:11.8f}".format(self.total / SATS_PER_BTC))
        tvl = self.total_output + self.total_wallet
        print("Total Value Locked: {:11.8f}".format(tvl / SATS_PER_BTC))
        print("Fees collected    : {:14.11f}".format(self.fees_collected / SATS_PER_BTC))
        self.all_last_updates.sort()
        if len(self.all_last_updates) > 0:
            median_index = len(self.all_last_updates) // 2
            if median_index * 2 == len(self.all_last_updates):
                median_value = (self.all_last_updates[median_index - 1] + self.all_last_updates[median_index]) // 2
            else:
                median_value = self.all_last_updates[median_index]
            print("Median age        : {:4.1f} days".format((NOW - median_value) / DAY))


my_node = Node()
my_node.print_status()


"""
print(clapi.getinfo())
print(clapi.listfunds())
print(clapi.listchannels(None,None))
"""
