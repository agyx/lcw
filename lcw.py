import json
import sys
import subprocess
import os


SATS_PER_BTC = 100000000


def cmd_funds(json_data):
    wallet_value_confirmed = 0
    wallet_value_unconfirmed = 0
    for output in json_data["outputs"]:
        if output["status"] == "confirmed":
            wallet_value_confirmed += output["value"]
        else:
            wallet_value_unconfirmed += output["value"]
    total_wallet = wallet_value_confirmed + wallet_value_unconfirmed
    print("Wallet funds (BTC):")
    print("- Confirmed:   {:11.8f}".format(wallet_value_confirmed / SATS_PER_BTC))
    print("- Unconfirmed: {:11.8f}".format(wallet_value_unconfirmed / SATS_PER_BTC))
    print("- TOTAL:       {:11.8f}".format(total_wallet / SATS_PER_BTC))

    print("Channels:")
    total_input = 0
    total_output = 0
    for channel in json_data["channels"]:
        total = channel["channel_total_sat"]
        output = channel["channel_sat"]
        input = total - output
        input_str = "{:11.8f}".format(input / SATS_PER_BTC) if input else " -         "
        output_str = "{:11.8f}".format(output / SATS_PER_BTC) if output else " -         "
        print("- {} {}-{}  {:11.8f}  {}".format(
            channel["peer_id"],
            input_str,
            output_str,
            total / SATS_PER_BTC,
            channel["state"]
        ))
        total_input += input
        total_output += output
    total = total_input + total_output
    print("Channels summary:")
    print("- Total input:  {:11.8f}".format(total_input / SATS_PER_BTC))
    print("- Total output: {:11.8f}".format(total_output / SATS_PER_BTC))
    print("- Grand total:  {:11.8f}".format(total / SATS_PER_BTC))
    tvl = total_output + total_wallet
    print("Total Value Locked: {:11.8f}".format(tvl / SATS_PER_BTC))


json_text = """
{
   "outputs": [
      {
         "txid": "05f1a96f2e27f2dde6c3bb7901eaf0110c5d5de8b9b647ed8929334fecf3773b",
         "output": 0,
         "value": 8550418,
         "amount_msat": "8550418000msat",
         "scriptpubkey": "0014755cf5553cd3d929e2f4801fbdee5da922b310d5",
         "address": "bc1qw4w024fu60vjnch5sq0mmmja4y3txyx4rtq9tj",
         "status": "confirmed",
         "blockheight": 689619,
         "reserved": false
      },
      {
         "txid": "fd563d8c5927ff65cb3bdff91279d4fd095bf402b9cf466ee20f9875b641302a",
         "output": 0,
         "value": 9259331,
         "amount_msat": "9259331000msat",
         "scriptpubkey": "00142a521f7430d75e5bdcad25b6b46a63a679b8ef48",
         "address": "bc1q9ffp7aps6a09hh9dykmtg6nr5eum3m6gds30xt",
         "status": "confirmed",
         "blockheight": 689716,
         "reserved": false
      },
      {
         "txid": "fcf6a4ec1d43d21cc76e38440981b26c1874c597c7710a90996106ab9d8b8cf6",
         "output": 0,
         "value": 9510418,
         "amount_msat": "9510418000msat",
         "scriptpubkey": "00148acbed1166dcd993110201b08c4b8729b7626fb8",
         "address": "bc1q3t976ytxmnvexygzqxcgcju89xmkymaca8nxu5",
         "status": "confirmed",
         "blockheight": 689716,
         "reserved": false
      },
      {
         "txid": "f2ad43d5cabaa00444a63bd583442113788c7ceca3441d0c47571d3cc5b16d75",
         "output": 1,
         "value": 9793148,
         "amount_msat": "9793148000msat",
         "scriptpubkey": "0014c400c23a5472c304ffa88258c59d69e73ecaf053",
         "address": "bc1qcsqvywj5wtpsflagsfvvt8tfuulv4uzn687lre",
         "status": "confirmed",
         "blockheight": 689717,
         "reserved": false
      }
   ],
   "channels": [
      {
         "peer_id": "03864ef025fde8fb587d989186ce6a4a186895ee44a926bfc370e2c366597a3f8f",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689480x319x1",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "98e0470bf85867170100cc1b034994e14145f58c3a550770495bc8b0fbee6a1e",
         "funding_output": 1
      },
      {
         "peer_id": "035e4ff418fc8b5554c5d9eea66396c227bd429a3251c8cbc711002ba215bfc226",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689491x306x1",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "bbb8c420af454ea55673db8ec4b51a4e20007c5b6028765a8703b6d07192c281",
         "funding_output": 1
      },
      {
         "peer_id": "0309bd6a02c71f288977b15ec3ac7283cfdd3d17dde65732981d5a718aa5fb0ebc",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689497x2293x0",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "8c78ea9741cb978ad84683dd565bd43ab03d669411802901a682fb34bf6e81c9",
         "funding_output": 0
      },
      {
         "peer_id": "02dfdcca40725ca204eec5d43a9201ff13fcd057c369c058ce4f19e5c178da09f3",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689515x803x0",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "412fc9819e116e46d29ed9a73885d00847b9cc6dc456c6e5c428c5d0991a60f4",
         "funding_output": 0
      },
      {
         "peer_id": "02b686ccf655ece9aec77d4d80f19bb9193f7ce224ab7c8bbe72feb3cdd7187e01",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689615x1720x0",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "96d97f16c99743c6177df368211614a66811b251892a0ff6883689d7609d0b47",
         "funding_output": 0
      },
      {
         "peer_id": "03c262d20edcf2acd25bc70139097bd7af3a4f691a178b8a88c9f52109d3cb6269",
         "connected": true,
         "state": "CHANNELD_NORMAL",
         "short_channel_id": "689619x1305x1",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "16039be289c48fda46a1a18c69de301a3a94235cc7ceb4d9c4c802af74792a8a",
         "funding_output": 1
      },
      {
         "peer_id": "0324b38edb883eea7f5268194dd7c4968f25828f5081c287378549d344b3b209e6",
         "connected": true,
         "state": "CHANNELD_AWAITING_LOCKIN",
         "channel_sat": 10000000,
         "our_amount_msat": "10000000000msat",
         "channel_total_sat": 10000000,
         "amount_msat": "10000000000msat",
         "funding_txid": "f2ad43d5cabaa00444a63bd583442113788c7ceca3441d0c47571d3cc5b16d75",
         "funding_output": 0
      }
   ]
}

"""

CLI_LIGHTNING_COMMAND_VARNAME = "CLI_LIGHTNING_COMMAND"
CLI_LIGHTNING_COMMAND = os.getenv(CLI_LIGHTNING_COMMAND_VARNAME)
if not CLI_LIGHTNING_COMMAND:
    print("{} env var is not set!".format(CLI_LIGHTNING_COMMAND_VARNAME))
    exit(1)

command = sys.argv[1]

if command == "funds":
    json_text = json.loads(subprocess.check_output([CLI_LIGHTNING_COMMAND, 'listfunds']))
    cmd_funds(json.loads(json_text))
