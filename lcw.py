#!/usr/bin/env python3

import json
import re
import string
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
#     list      peer id      capacity
# -----------------------------------------
# 1   wp only   very short   bars
# 2 * wp only   short        bars
# 3   all       short        bars
# 4   all       short        values
# 5   all       long         values


class ConditionSign:
    PLUS = "+"
    MINUS = "-"

    def __init__(self):
        pass


class ConditionOp:
    OP_EQUAL = "="
    OP_NOT_EQUAL = "<>"
    OP_GREATER = ">"
    OP_GREATER_OR_EQUAL = ">="
    OP_LOWER = "<"
    OP_LOWER_OR_EQUAL = "<="
    OP_TRUE = "any"
    OP_FALSE = "none"


def eval_arg(obj, arg):
    if arg is None:
        return None
    try:
        return float(arg)
    except Exception:
        if arg in obj:
            return obj[arg]
        else:
            return arg
    # return arg


class StateFilter:
    OR = "or"
    AND = "and"
    NOT = "not"

    def __init__(self, op):
        self.op = op


class ObjCondition:
    def __init__(self, string):
        self.left = None
        self.right = None
        self.op = ConditionOp.OP_TRUE
        regexp = re.compile("([\w]+)$")
        m = regexp.match(string)
        if m:
            self.left = None
            self.right = None
            self.op = string
            return
        regexp = re.compile("([\w]+)[\s]*([<>=]+)[\s]*([\w]+)$")
        m = regexp.match(string)
        if m:
            self.left = m.group(1)
            self.op = m.group(2)
            self.right = m.group(3)
            return
        print("malformed object condition: " + string)

    def exec(self, obj):
        if self.op == ConditionOp.OP_TRUE:
            return True
        elif self.op == ConditionOp.OP_FALSE:
            return False
        left = eval_arg(obj, self.left)
        right = eval_arg(obj, self.right)
        try:
            if self.op == ConditionOp.OP_EQUAL:
                return left == right
            elif self.op == ConditionOp.OP_NOT_EQUAL:
                return left != right
            elif self.op == ConditionOp.OP_GREATER:
                return left > right
            elif self.op == ConditionOp.OP_GREATER_OR_EQUAL:
                return left >= right
            elif self.op == ConditionOp.OP_LOWER:
                return left < right
            elif self.op == ConditionOp.OP_LOWER_OR_EQUAL:
                return left <= right
            else:
                return False
        except Exception:
            return False


# class ObjFilter:
#     def __init__(self, string):
#         pass


class FilterPipe:
    def __init__(self):
        self.filters = []

    def add_filter(self, string):
        if string.startswith("+"):
            sign = ConditionSign.PLUS
            condition = string[1:]
        elif string.startswith("-"):
            sign = ConditionSign.MINUS
            condition = string[1:]
        else:
            sign = ConditionSign.PLUS
            condition = string
        condition = condition.strip()
        filter = None
        if condition == StateFilter.OR:
            filter = StateFilter(StateFilter.OR)
        elif condition == StateFilter.AND:
            filter = StateFilter(StateFilter.AND)
        elif condition == StateFilter.NOT:
            filter = StateFilter(StateFilter.NOT)
        if filter is not None:
            self.filters += [filter]
        else:
            self.filters += [(sign, ObjCondition(condition))]

    def exec(self, obj):
        result = True
        for filter in self.filters:
            if isinstance(filter, StateFilter):
                if filter.op == StateFilter.OR:
                    if result:
                        return True
                elif filter.op == StateFilter.AND:
                    if not result:
                        return False
                elif filter.op == StateFilter.NOT:
                    result = not result
            else:
                (sign, condition) = filter
                condition_result = condition.exec(obj)
                if sign == ConditionSign.PLUS and condition_result:
                    result = True
                elif sign == ConditionSign.MINUS and condition_result:
                    result = False
        return result


def file_content(path):
    try:
        file = open(path, mode="r")
        content = file.read()
        file.close()
        return json.loads(content)
    except Exception:
        print("file not found: " + path)
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


def age_string2(age_days):
    age = age_days
    if age < 1:
        return "   today "
    days = int(age)
    if days == 1:
        return " 1 day   "
    elif days < 90:
        return "{:2d} days  ".format(days)
    else:
        return "{:2d} months".format((days + 15) // 30)


def peer_id_string(alias, peer_id, verbosity):
    filtered_alias = filter_alias(alias)
    if verbosity == 5:
        return "{:24.24} {}".format(filtered_alias, peer_id)
    elif verbosity == 1:
        return "{:12.12} {}...".format(
            filtered_alias,
            peer_id[:4],
        )
    else:
        return "{:16.16} {}...{}".format(
            filtered_alias,
            peer_id[:8],
            peer_id[-8:],
        )


def capacity_string(input, output, verbosity):
    BAR_CHAR = "="
    total = input + output
    if verbosity <= 3:
        input_bars = round(input / total * 10)
        output_bars = round(output / total * 10)
        return "{:>10.10}|{:<10.10} {:11.8f}".format(
            BAR_CHAR * input_bars,
            BAR_CHAR * output_bars,
            total / SATS_PER_BTC
        )
    else:
        input_str = "{:10.8f}".format(
            input / SATS_PER_BTC) if input else "          "
        output_str = "{:10.8f}".format(
            output / SATS_PER_BTC) if output else "          "
        return "{}-{}  {:10.8f}".format(
            input_str,
            output_str,
            total / SATS_PER_BTC
        )


def day(days_ago=0):
    return time.strftime("%Y%m%d", time.localtime(NOW - days_ago * 86400))


def timestamp_from_day(day):
    return int(time.mktime(time.strptime(day + " 00:00:00", '%Y%m%d %H:%M:%S')))


def filter_alias(alias):
    result = ""
    for ch in alias:
        if ch in string.printable:
            result += ch
        else:
            result += "!"
    return result


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

    def listchannels(self, short_channel_id="null", source_node_id="null"):
        if self.test_mode:
            if source_node_id == "null":
                return file_content("tests/listchannels-all.txt")
            else:
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
        self.date_ref = None
        self.since = None
        self.ref_data = None
        self.ignored_channels = []
        data_stored = file_content(LCW_DATA_PATH)
        if data_stored is not None:
            if "ignored" in data_stored:
                self.ignored_channels = data_stored["ignored"]
            if since is not None:
                history = data_stored["history"]
                self.date_ref = day(since)
                if self.date_ref in history:
                    self.ref_data = history[self.date_ref]
                    self.period = (NOW - timestamp_from_day(self.date_ref)) / 86400
                    self.since = since
        self.getinfo = clapi.getinfo()
        self.id = self.getinfo["id"]
        self.fees_collected = self.getinfo["msatoshi_fees_collected"] / 1000
        self.listfunds = clapi.listfunds()
        self.listchannels = clapi.listchannels(source_node_id=self.id)
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
                                  short_id=short_channel_id,
                                  input_capacity=input,
                                  output_capacity=output,
                                  total_capacity=input + output,
                                  state=channel_data["state"],
                                  last_update=NOW,
                                  in_payments_offered=0,
                                  out_payments_offered=0,
                                  in_payments=0,
                                  out_payments=0,
                                  in_msatoshi_fulfilled=0,
                                  out_msatoshi_fulfilled=0,
                                  in_msatoshi_offered=0,
                                  out_msatoshi_offered=0,
                                  new_channel=new_channel,
                                  total_payments=0,
                                  base_fee_msat=0,
                                  ppm_fee=0,
                                  alias="?",
                                  routed_amount=0,
                                  routed_capacity=0,
                                  total_payments_offered=None,
                                  settle_rate=None)
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
                channel.in_payments_offered = channel_data["in_payments_offered"]
                channel.out_payments_offered = channel_data["out_payments_offered"]
                channel.in_payments = channel_data["in_payments_fulfilled"]
                channel.out_payments = channel_data["out_payments_fulfilled"]
                channel.in_msatoshi_fulfilled = channel_data["in_msatoshi_fulfilled"]
                channel.out_msatoshi_fulfilled = channel_data["out_msatoshi_fulfilled"]
                channel.in_msatoshi_offered = channel_data["in_msatoshi_offered"]
                channel.out_msatoshi_offered = channel_data["out_msatoshi_offered"]
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
                    if "in_msatoshi_offered" in channel_ref:
                        channel.in_payments_offered -= channel_ref["in_payments_offered"]
                        channel.out_payments_offered -= channel_ref["out_payments_offered"]
                        channel.in_msatoshi_offered -= channel_ref["in_msatoshi_offered"]
                        channel.out_msatoshi_offered -= channel_ref["out_msatoshi_offered"]
                channel.total_payments_offered = (channel.in_payments_offered + channel.out_payments_offered)
                channel.routed_amount = (channel.in_msatoshi_fulfilled + channel.out_msatoshi_fulfilled) / 1000
                channel.routed_capacity = channel.routed_amount / channel.total_capacity
                channel.total_payments = channel.in_payments + channel.out_payments
                if channel.total_payments_offered != 0:
                    channel.settle_rate = channel.total_payments / channel.total_payments_offered * 100
                self.in_payments += channel.in_payments
                self.out_payments += channel.out_payments
                self.routed_amount += (channel.in_msatoshi_fulfilled + channel.out_msatoshi_fulfilled) / 2 / 1000
        for (channel_id, channel) in self.channels.items():
            channel_ref = self.get_channel_ref(channel_id)
            if channel.new_channel:
                channel.funding_block = self.block_height
            else:
                channel.funding_block = int(channel_id.split("x")[0])
            channel.age = (self.block_height - channel.funding_block) * 600 / 86400
            if channel_ref is not None:
                period = self.period
            else:
                period = channel.age
            if period <= 0:
                channel.tx_per_day = 0
            else:
                channel.tx_per_day = channel.total_payments / period
            # if channel.output_capacity == 0:
            #    channel.used_capacity = 1000
            # else:
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
        if self.ref_data is not None and channel_id in self.ref_data:
            return self.ref_data[channel_id]
        else:
            return None

    def set_fees(self, force, k, offset, max_ppm):
        DEFAULT_BASE_FEE = 0
        for (channel_id, channel) in self.channels.items():
            out_ratio = channel.output_capacity / (channel.input_capacity + channel.output_capacity)
            if channel.ppm_fee == 0 and not force:
                print("{:13s} skipped".format(channel_id))
                continue
            elif out_ratio == 0:
                new_ppm_fee = max_ppm
            else:
                new_ppm_fee = int(round(k / out_ratio + offset, -1))
                if new_ppm_fee > max_ppm:
                    new_ppm_fee = max_ppm
            if channel.base_fee_msat == DEFAULT_BASE_FEE and new_ppm_fee == channel.ppm_fee:
                continue
            clapi.setchannelfee(channel_id, DEFAULT_BASE_FEE, new_ppm_fee)
            print("{:13s} {:4.0f}%  {:5d}/{:5d} -> {:5d}/{:5d}".format(channel_id,
                                                                       out_ratio * 100,
                                                                       channel.base_fee_msat,
                                                                       channel.ppm_fee,
                                                                       DEFAULT_BASE_FEE,
                                                                       new_ppm_fee))

    def print_channel(self, channel, verbosity):
        # "- {short_id:13s}  {peer_info}  {cap_info}  {payments_info}  {age_info}  {tx_per_day:5.1f}  {routed_capacity:6.2f}  {state} ({base_fee_msat}/{ppm_fee})"
        payments_str = "{:8s} {:4d}".format(
            "{:4d}-{:<d}".format(
                channel.in_payments,
                channel.out_payments),
            channel.total_payments,
        )
        settle_rate_str = "{:5.1f}%".format(channel.settle_rate) if channel.settle_rate is not None else "  n/a "
        print("- {:13s}  {}  {}  {}  {}  {:5.1f}  {:6.2f}  {}  {} ({}/{})".format(
            channel.short_id,
            peer_id_string(channel.alias, channel.peer_id, verbosity),
            capacity_string(channel.input_capacity, channel.output_capacity, verbosity),
            payments_str,
            age_string2(channel.age),
            channel.tx_per_day,
            channel.routed_capacity,
            # age_string(channel.last_update),
            settle_rate_str,
            channel.state,
            channel.base_fee_msat,
            channel.ppm_fee
        ))

    def print_status(self, verbosity=2, sort_key=None, limit=0, filters=None):
        if not filters:
            if verbosity <= 2:
                filters = ["-any", "total_payments>0", "age<1", "state<>CHANNELD_NORMAL"]
            else:
                filters = []
        pipe = FilterPipe()
        for filter in filters:
            pipe.add_filter(filter)
        print("Wallet funds (BTC):")
        print("- Confirmed:   {:11.8f}".format(self.wallet_value_confirmed / SATS_PER_BTC))
        print("- Unconfirmed: {:11.8f}".format(self.wallet_value_unconfirmed / SATS_PER_BTC))
        print("- TOTAL:       {:11.8f}".format(self.total_wallet / SATS_PER_BTC))
        for channel_id in self.ignored_channels:
            if channel_id in self.channels:
                del self.channels[channel_id]
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
            if not pipe.exec(channel):
                continue
            count += 1
            self.print_channel(channel, verbosity)
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

    def store_today_data(self):
        stored_data = file_content(LCW_DATA_PATH)
        if stored_data is None:
            stored_json = {}
        else:
            stored_json = stored_data
        today = day()
        history = stored_json["history"]
        if today in history:
            print("today's data is already stored")
            return
        history[today] = self.channels
        file = open(LCW_DATA_PATH, "w")
        file.write(json.dumps(stored_json))
        file.close()


parser = OptionParser()

parser.add_option("-t", "--test",
                  action="store_true", dest="test_mode", default=False,
                  help="Test mode")

parser.add_option("-v", "--verbosity",
                  action="store", type="int", dest="verbosity", default=2,
                  help="Verbosity level: 1 to 5")

parser.add_option("-l", "--limit",
                  action="store", type="int", dest="limit", default=0,
                  help="Limit number of channels logged to provided parameter")

parser.add_option("-f", "--filter",
                  action="append", type="string", dest="filters", default=[],
                  help="Add a display filter")

parser.add_option("", "--force",
                  action="store_true", dest="force", default=False,
                  help="Do not skip 0 fees settings")

parser.add_option("-s", "--sort",
                  action="store", type="string", dest="sort_key", default=None,
                  help="Sort channels with provided key")

parser.add_option("-i", "--ignore",
                  action="store", type="string", dest="ignored_channel", default=None,
                  help="Ignore the specified channel for ever")

parser.add_option("", "--since",
                  action="store", type="int", dest="since", default=None,
                  help="Payments and derived stats are counted from given # of days")

parser.add_option("", "--amount",
                  action="store", type="int", dest="amount", default=15000000,
                  help="Amount for new channel when searching for best peers")

parser.add_option("", "--fees",
                  action="store", type="string", dest="fees", default="50/-40/2000",
                  help="Set ppm fees from a string <k>/<offset>/<max>"
                       "Base fee is always 0")

parser.add_option("", "--bestpeers",
                  action="store_true", dest="bestpeers", default=False,
                  help="Search for best connectivity peers")

parser.add_option("", "--channels",
                  action="store_true", dest="channels", default=False,
                  help="Analyze connectivity contribution of node's current channels")

parser.add_option("", "--channel",
                  action="store", dest="channel", default=None,
                  help="Display all details about a specified channel")

parser.add_option("", "--bestnodes",
                  action="store_true", dest="bestnodes", default=False,
                  help="Search for best connected nodes")

parser.add_option("", "--node",
                  action="store", type="string", dest="node", default=None,
                  help="Analyze node")

parser.add_option("", "--command",
                  action="store", type="string", dest="command", default="status",
                  help="store: Store current channels information into json history file\n"
                       "status:\n"
                       "setfees:\n"
                       "analyze:\n"
                  )

(options, args) = parser.parse_args()

clapi = CLightning(test_mode=options.test_mode)

if options.command != "status":
    options.since = None

my_node = Node(since=options.since)


def ignore_channel(channel_id):
    stored_data = file_content(LCW_DATA_PATH)
    if stored_data is None:
        stored_json = {}
    else:
        stored_json = stored_data
    if "ignored" in stored_json:
        ignored = stored_json["ignored"]
    else:
        ignored = []
        stored_json["ignored"] = ignored
    ignored += [channel_id]
    file = open(LCW_DATA_PATH, "w")
    file.write(json.dumps(stored_json))
    file.close()


if options.command == "store":
    my_node.store_today_data()
elif options.ignored_channel:
    ignore_channel(options.ignored_channel)
elif options.command == "setfees":
    fees = options.fees.split("/")
    my_node.set_fees(options.force, int(fees[0]), int(fees[1]), int(fees[2]))
elif options.command == "status":
    if options.channel is not None:
        selected = []
        for peer in my_node.listpeers["peers"]:
            if peer["id"] == options.channel:
                selected = [peer]
                break
            if options.channel in peer["id"]:
                selected += [peer]
                continue
            for channel in peer["channels"]:
                if channel["short_channel_id"] == options.channel:
                    selected = [channel]
                    break
            if len(selected) > 0:
                break
            # search short channel ids
        if selected:
            for item in selected:
                print(json.dumps(item, indent=3))
                print("--------------------------")
        else:
            print("specified id not found in peers list")
    else:
        my_node.print_status(verbosity=options.verbosity,
                             sort_key=options.sort_key,
                             limit=options.limit,
                             filters=options.filters)
elif options.command == "analyze":
    print("getting all channels...")
    channels = clapi.listchannels()
    print("building the network...")
    nodes = {}
    for channel in channels["channels"]:
        source = channel["source"]
        if source in nodes:
            node = nodes[source]
        else:
            node = munch.Munch(
                node_id=source,
                channels=[]
            )
            nodes[source] = node
        node.channels += [munch.Munch.fromDict(channel)]
        # if "satoshis" not in channel:
        #     print(channel)


    def centrality_map2(node_id, new_peer=None, without_index=None):
        start_node = nodes[node_id]
        removed_channel = None
        if new_peer is not None:
            start_node.channels += [munch.Munch(source=node_id,
                                                destination=new_peer[0],
                                                public=True,
                                                satoshis=new_peer[1])]
        elif without_index is not None:
            removed_channel = start_node.channels.pop(without_index)
        visited = {}
        newly_visited = {}
        visited[start_node.node_id] = (start_node, 0)
        newly_visited[start_node.node_id] = (start_node, 0)
        hops = []
        for depth in range(1, 10):
            next_newly_visited = {}
            for neighbour in newly_visited.values():
                for channel in neighbour[0].channels:
                    # if not channel.public:
                    #     continue
                    if channel.destination not in nodes:
                        pass
                        # print("node not found: " + channel.destination)
                    else:
                        new_node = nodes[channel.destination]
                        if new_node.node_id not in visited and new_node.node_id not in newly_visited:
                            if new_node.node_id in next_newly_visited:
                                old_entry = next_newly_visited[new_node.node_id]
                                next_newly_visited[new_node.node_id] = (new_node, old_entry[1] + channel.satoshis)
                            else:
                                next_newly_visited[new_node.node_id] = (new_node, channel.satoshis)
            # print("{} hops: {} nodes".format(depth, len(next_newly_visited)))
            visited.update(newly_visited)
            newly_visited = next_newly_visited
            if len(newly_visited) == 0:
                break
            hop_sum = 0
            for (node, sats) in newly_visited.values():
                # print(node_entry)
                hop_sum += sats
            hops += [hop_sum / SATS_PER_BTC]
        if new_peer is not None:
            start_node.channels.pop()
        elif without_index is not None:
            start_node.channels.insert(without_index, removed_channel)
        return hops


    def centrality_map1(node_id, new_peer=None, without_index=None):
        start_node = nodes[node_id]
        removed_channel = None
        if new_peer is not None:
            start_node.channels += [munch.Munch(source=node_id,
                                                destination=new_peer,
                                                public=True)]
        elif without_index is not None:
            removed_channel = start_node.channels.pop(without_index)
        visited = {}
        newly_visited = {}
        visited[start_node.node_id] = start_node
        newly_visited[start_node.node_id] = start_node
        hops = []
        for depth in range(1, 10):
            next_newly_visited = {}
            for neighbour in newly_visited.values():
                for channel in neighbour.channels:
                    # if not channel.public:
                    #     continue
                    if channel.destination not in nodes:
                        pass
                        # print("node not found: " + channel.destination)
                    else:
                        new_node = nodes[channel.destination]
                        if new_node.node_id not in visited and new_node.node_id not in newly_visited:
                            next_newly_visited[new_node.node_id] = new_node
            # print("{} hops: {} nodes".format(depth, len(next_newly_visited)))
            visited.update(newly_visited)
            newly_visited = next_newly_visited
            if len(newly_visited) == 0:
                break
            hops += [len(newly_visited)]
        if new_peer is not None:
            start_node.channels.pop()
        elif without_index is not None:
            start_node.channels.insert(without_index, removed_channel)
        return hops


    def centrality_score(hops):
        depth = 1
        wsum = 0
        hop_sum = 0
        for hop in hops:
            wsum += hop * (1 / depth)
            depth += 1
            hop_sum += hop
        wsum /= hop_sum
        return round(wsum * 1000)


    def analyze(node_id, new_peer=None):
        print("Node {} {}".format(my_node.hashed_listnodes[node_id], node_id))
        hops = centrality_map2(node_id, new_peer=new_peer)
        print("- hops: {}".format(hops))
        score = centrality_score(hops)
        print("- centrality score: {}".format(score))
        return score


    if options.node is not None:
        if options.node == "self":
            node_id = my_node.id
        else:
            node_id = options.node
        print("Node {} {}".format(my_node.hashed_listnodes[node_id], node_id))
        channel_hops = centrality_map2(node_id)
        print("- hops: {}".format(channel_hops))
        score = centrality_score(channel_hops)
        print("- centrality score: {}".format(score))
    elif options.bestpeers:
        print("Searching for best connectivity peers with new capacity: {} sats".format(options.amount))
        if options.limit > 0:
            limit = options.limit
        else:
            limit = 15
        current_score = analyze(my_node.id)
        score_board = []
        for node in nodes.values():
            if len(node.channels) < 25:
                continue
            channel_hops = centrality_map2(my_node.id, new_peer=(node.node_id, options.amount))
            new_score = centrality_score(channel_hops)
            if new_score <= current_score:
                continue
            score_board += [(node, new_score)]
            score_board.sort(key=lambda x: x[1], reverse=True)
            count = 0
            print()
            for score in score_board:
                count += 1
                print("{:3d}  {:24.24} {}: {} ({:+d})".format(count,
                                                              filter_alias(my_node.hashed_listnodes[score[0].node_id]),
                                                              score[0].node_id,
                                                              score[1],
                                                              score[1] - current_score))
                if count == limit:
                    break
            print()
    elif options.bestnodes:
        print("Searching for best connected nodes")
        if options.limit > 0:
            limit = options.limit
        else:
            limit = 15
        score_board = []
        for node in nodes.values():
            if len(node.channels) < 25:
                continue
            print()
            channel_hops = centrality_map2(node.node_id)
            new_score = centrality_score(channel_hops)
            score_board += [(node, new_score)]
            score_board.sort(key=lambda x: x[1], reverse=True)
            count = 0
            print()
            for score in score_board:
                count += 1
                print("{:3d}  {:24.24} {}: {}".format(count,
                                                      filter_alias(my_node.hashed_listnodes[score[0].node_id]),
                                                      score[0].node_id,
                                                      score[1]))
                if count == limit:
                    break
    elif options.channels:
        channels = nodes[my_node.id].channels
        index = 0
        hops = centrality_map2(my_node.id)
        node_score = centrality_score(hops)
        print("Node current score: {}".format(node_score))
        no_contrib_aliases = []
        for channel in channels:
            channel_hops = centrality_map2(channel.destination)
            channel_score = centrality_score(channel_hops)
            node_hops = centrality_map2(my_node.id, without_index=index)
            contrib_score = centrality_score(node_hops)
            contrib = node_score - contrib_score
            alias = filter_alias(my_node.hashed_listnodes[channel.destination])
            if contrib > 0:
                print("{:24.24} {} {:8d}: {} {:+d}".format(alias,
                                                           channel.destination,
                                                           channel.satoshis,
                                                           channel_score,
                                                           contrib))
            else:
                no_contrib_aliases += [alias]
            index += 1
        print("No connectivity contribution: " + ", ".join(no_contrib_aliases))

"""
print(clapi.getinfo())
print(clapi.listfunds())
print(clapi.listchannels(None,None))
"""

"""
p = re.compile("([\w]+)[\s]*([<>=]+)[\s]*([\w]+)")
m = p.match("age>= 25")
if m:
    print('Match found: ', m.group(1))
    print('Match found: ', m.group(2))
    print('Match found: ', m.group(3))
else:
    print('No match')


args = [1,2,3]
print("{} {} {}".format(*args))
"""
