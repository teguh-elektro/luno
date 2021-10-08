import requests
import numpy as np
import pandas as pd
import arrow
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv('KEY') 
sign = os.getenv('SIGN')
pair = os.getenv('PAIR')
min_idr = float(os.getenv('MIN_IDR') )
min_coin = float(os.getenv('MIN_COIN') )
min_rsi = float(os.getenv('MIN_RSI'))
max_rsi = float(os.getenv('MAX_RSI'))
profit = float(os.getenv('PROFIT'))
used_idr = float(os.getenv('USED_IDR'))
idr = pair[3:6]
coin = pair[0:3]



def rma(x, n, y0):
    a = (n-1) / n
    ak = a**np.arange(len(x)-1, -1, -1)
    return np.r_[np.full(n, np.nan), y0, np.cumsum(ak * x) / ak / n + y0 * a**np.arange(1, len(x)+1)]
    
def get_candles():
    end_time = arrow.utcnow().shift(hours=7)
    start_time = end_time.shift(days=-1).format('X')
    end_time = end_time.format('X')
    params = {
        "symbol": pair,
        "from": int(start_time.split('.')[0]),
        "to": int(end_time.split('.')[0]),
        "resolution": "5"
    }
    response = requests.get('https://ajax.luno.com/ajax/1/udf/history',
                params=params)
    response = response.json()
    if(response.get('s', False) == 'ok'):
        n = 14
        df = pd.DataFrame(response, columns=['h', 'l', 'o', 'c', 't', 'v'])
        df['t'] = pd.to_datetime(df.t, unit='s') + pd.Timedelta('07:00:00')
        df['v'] = pd.to_numeric(df.v)
        df.set_index('t', inplace=True)
        df['c'] = pd.to_numeric(df['c'])
        df['change'] = df['c'].diff()
        df['gain'] = df.change.mask(df.change < 0, 0.0)
        df['loss'] = -df.change.mask(df.change > 0, -0.0)
        df['avg_gain'] = rma(df.gain[n+1:].to_numpy(), n, np.nansum(df.gain.to_numpy()[:n+1])/n)
        df['avg_loss'] = rma(df.loss[n+1:].to_numpy(), n, np.nansum(df.loss.to_numpy()[:n+1])/n)
        df['rs'] = df.avg_gain / df.avg_loss
        df['rsi_14'] = 100 - (100 / (1 + df.rs))
        return (True, float(df[-1:].c.values[0]), float(df[-1:].rsi_14.values[0]))
    return(False, 0, 0)

def get_balance(idr, coin):
    res = requests.get('https://api.luno.com/api/1/balance',
                auth = HTTPBasicAuth(key, sign))
    res = res.json()
    if(res.get('balance', False)):
        balances = res['balance']
        idr_wallet = float([balance['balance'] for balance in balances if balance['asset'] == idr][0])
        coin_wallet = float([balance['balance'] for balance in balances if balance['asset'] == coin][0])
        return(True, idr_wallet, coin_wallet)
    else:
        return(False, 0, 0)

def buy(pair, stop_price, idr_wallet):
    stop_price = str(stop_price).split('.')[0]
    volume = float(idr_wallet)/float(stop_price)
    params = {
        "pair": pair,
        "type": "BID",
        "stop_direction": "ABOVE",
        "stop_price": stop_price,
        "price": stop_price,
        "volume": str(volume)[0:6], # max number length
    }
    res = requests.post('https://api.luno.com/api/1/postorder',
                auth = HTTPBasicAuth(key, sign),
                params=params)
    res = res.json()
    if(res.get('order_id', False)):
        return(True, "")
    else:
        return(False, res)

def sell(pair, stop_price, volume):
    params = {
        "pair": pair,
        "type": "ASK",
        "stop_direction": "BELOW",
        "stop_price": stop_price,
        "price": stop_price,
        "volume": str(volume)[0:6], # max number length
    }
    res = requests.post('https://api.luno.com/api/1/postorder',
                auth = HTTPBasicAuth(key, sign),
                params=params)
    res = res.json()
    if(res.get('order_id', False)):
        return(True, "")
    else:
        return(False, res)

def cancel_order(order_id):
    res = requests.post(f'https://api.luno.com/api/1/stoporder?order_id={order_id}',
                auth = HTTPBasicAuth(key, sign))
    res = res.json()
    if(res.get('success', False)):
        return True
    else:
        return False

def get_orders():
    params = {
        "pair": pair
    }
    fee = requests.get(f'https://api.luno.com/api/1/fee_info',
                auth = HTTPBasicAuth(key, sign),
                params = params)
    fee = fee.json()
    maker_fee = float(fee.get('maker_fee', 0))
    taker_fee = float(fee.get('taker_fee', 0))

    res = requests.get(f'https://api.luno.com/api/exchange/2/listorders',
                auth = HTTPBasicAuth(key, sign),
                params = params)
    res = res.json()
    if(res.get('orders', False)):
        ao = pd.json_normalize(res['orders'])
        if(len(ao) > 0):
            order_id = ao[:1].order_id.values[0]
            limit_price = float(ao[:1].limit_price.values[0])
            limit_volume = float(ao[:1].limit_volume.values[0])
            type_order = ao[:1].side.values[0]
            type_order = type_order == 'BUY'
            return(True, order_id, False, limit_price, limit_volume, type_order)
    else:
        res = requests.get(f'https://api.luno.com/api/1/listorders',
            auth = HTTPBasicAuth(key, sign),
            params = params)
        res = res.json()
        if(res.get('orders', False)):
            od = pd.json_normalize(res['orders'])
            od = od[od.completed_timestamp != 0]
            co = od[od.state == 'COMPLETE'][:1]
            if(len(co) > 0):
                order_id = co[:1].order_id.values[0]
                limit_price = float(co[:1].limit_price.values[0])
                limit_volume = float(co[:1].limit_volume.values[0])
                type_order = co[:1].type.values[0]
                type_order = (type_order == 'BID') | (type_order == 'BUY')
                if(type_order == True):
                    limit_volume = limit_volume - (limit_volume * taker_fee)
                else:
                    limit_volume = limit_volume - (limit_volume * maker_fee)
                return(True, order_id, True, limit_price, limit_volume, type_order)
            po = od[od.state == 'PENDING'][:1]
            if(len(po) > 0):
                order_id = po[:1].order_id.values[0]
                limit_price = float(po[:1].limit_price.values[0])
                limit_volume = float(po[:1].limit_volume.values[0])
                type_order = po[:1].type.values[0]
                type_order = (type_order == 'BID') | (type_order == 'BUY')
                if(type_order == True):
                    limit_volume = limit_volume - (limit_volume * taker_fee)
                else:
                    limit_volume = limit_volume - (limit_volume * maker_fee)
                return(True, order_id, False, limit_price, limit_volume, type_order)
        else:
            return(True, "", True, 0, 0, False)
    return(False, "", False, 0, 0, False)

def lambda_handler(event, context):   
    # MAIN
    print('START!')
    is_success, idr_wallet, coin_wallet = get_balance(idr, coin) 
    if(not is_success):
        print("! FAILED GET BALANCE")
        return -1
    is_success, close_price, rsi = get_candles()
    if(not is_success):
        print("! FAILED GET TRADES DATA")
        return -1
    is_success, order_id, is_complete, limit_price, limit_volume, is_buy = get_orders()
    if(not is_success):
        print("! FAILED GET ORDER DATA")
        return -1
    profit = round((close_price * limit_volume) - (limit_price * limit_volume))
    print(f'''
        SUMARRY: Rp.{round(close_price * limit_volume)} ({'+' if(profit >= 0) else '-'}Rp.{profit})
        CLOSE: {close_price}
        RSI NOW: {round(rsi)}%
        {coin}: {coin_wallet}
        {idr}: Rp.{round(idr_wallet)}
        ORDER ID: {order_id}
        LATEST STATUS: {"WAITING ORDER" if(not is_complete) else "COMPLETE"} {"BUY" if(is_buy) else "SELL"}
        LIMIT PRICE: {limit_price}
        LIMIT VOLUME: {limit_volume}
    ''')
    
    if(not is_complete):
        if((rsi > min_rsi) & (rsi < max_rsi)):
            if(not is_buy & (limit_price > close_price)):
                cancel_order(order_id)
                print('> CANCEL BUY ORDER')
                return 0 
            elif(is_buy & (limit_price < close_price)):
                cancel_order(order_id)
                print('> CANCEL SELL ORDER')
                return 0 
            else:
                print(f'> WAITING TO {"BUY" if(is_buy) else "SELL"}...')
                return 0    
        else:
            print(f'> WAITING TO {"BUY" if(is_buy) else "SELL"}...')
            return 0 

    if((idr_wallet >= min_idr) and (not is_buy)):
        if(rsi < min_rsi):
            if(limit_price == 0):
                is_success, error = buy(pair, close_price, used_idr if(idr_wallet >= used_idr) else idr_wallet)
            else:
                is_success, error = buy(pair, close_price, (limit_volume * limit_price) if(idr_wallet >= (limit_volume * limit_price)) else idr_wallet)
            if(not is_success):
                print("! FAILED BUY")
                print(error)
                return -1
            print('> REQUEST BUY IS SENT')
        else:
            print('> RSI BUY SIGNAL DOESN\'T MATCH')

    elif((coin_wallet >= min_coin) and is_buy):
        if(rsi > max_rsi):
            saved_close_price = float(limit_price)
            saved_close_price = saved_close_price + (saved_close_price * profit) 
            if(saved_close_price <= close_price):
                is_success, error = sell(pair, close_price, coin_wallet)    
                if(not is_success):
                    print("! FAILED SELL")
                    print(error)
                    return -1  
                print('> REQUEST SELL IS SENT')
            else:
                print('> PRICE IS TOO LOW')
        else:
            print('> RSI SELL SIGNAL DOESN\'T MATCH')
    else:
        print("> EMPTY WALLET!")

    print('SLEEPING...')

lambda_handler(None, None)

