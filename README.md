# Directional Scalper
## A hedge scalping strategy based on directional analysis using a quantitative approach
### Supports Bybit only, other exchanges coming soon

### Links
* Dashboard: https://tradesimple.xyz
* API: http://api.tradesimple.xyz/data/quantdata.json

![](https://github.com/donewiththedollar/directional-scalper/blob/main/directional-scalper.gif)
# Instructions
* Install requirements
> pip3 install -r requirements.txt
### Setting up the bot
 1. Create config.json from config.json.example
 2. Enter exchange_api_key and exchange_api_secret
 3. Check/fill all other options. For telegram see below

 1. Get token from botfather after creating new bot, send a message to your new bot
 2. Go to https://api.telegram.org/bot<bot_token>/getUpdates
 3. Replacing <bot_token> with your token from the botfather after creating new bot
 4. Look for chat id and copy the chat id into config.json

### Starting the bot
* Hedge mode is recommended, but you can of course use the other modes as well. Low lot size is recommended.
> python3 bot.py --mode hedge --symbol GALAUSDT --iqty 1 --tg off --config config.json --avoidfees on
* Starting the bot in debug mode for inverse perpetuals BTCUSD
* Inverse is currently short only, used as a hedge against your BTC balance, to accumulate BTC with no risk, no losses
> python3 bot_inverse_debugmode.py --mode inverse --symbol BTCUSD --iqty 1 --tg off

### Parameters
> --avoidfees [on, off]
* only use one or the other [avoidfees, or deleverage]
> --deleverage [on, off]
* --mode [hedge, long, short, presistent, longbias, btclinear-long, btclinear-short
> Some modes are in development, hedge mode is the recommended mode that has proven to be profitable and allows you to control your risk accordingly.


### Docker
To run the bot inside docker container use the following command:
> docker-compose run directional-scalper python3 bot.py --mode hedge --symbol GALAUSDT --iqty 1 --tg off

* There are five modes:
> long, short, hedge, persistent, inverse, violent
* To do:
> Instance manager


### Donations
If you would like to show your appreciation for this project through donations, there are a few addresses here to choose from
* **BTC**: bc1qu5p292xs9jvu0vuanjcpsqszmg4hkmrrahdpj7
* **XMR**: 42wS15cGdMmU4xciT4PV6XaqtEuc2PXn3DP5ymNb1BkDVU3j2TXzdkze2iSMqc64KhCsGC4FpU866P38QneBNqQi4ui1Cvg
* **DOGE**: D9iNDsVpJaXqChmveCUsvnM87sQo5Tcia6
