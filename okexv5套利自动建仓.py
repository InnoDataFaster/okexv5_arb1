"""
邢不行2021策略分享会
OKV5 套利
邢不行微信：xbx1717
"""
from pprint import pprint

import ccxt
from Functions import *
from config import *

# =====创建ccxt的okex交易所
exchange = ccxt.okex()  # 如果是最新版的ccxt，也可以ccxt.okex()
exchange.apiKey = apiKey
exchange.secret = secret
exchange.password = password  # okex在api的时候，需要填写一个Passphrase，把Passphrase填写到这里即可
exchange.load_markets()

# =====套利初始化操作
# 获取各个标的的下单价格精度、数量精度、最大杠杆倍数
coin_info = get_precision(exchange, coin_info, trading_pair)
# 获取交易手续费
coin_info = get_fee_rate(exchange, coin_info, trading_pair)
# 获取最大实际杠杆
max_leverage = get_max_leverage(exchange, execute_amount, coin_info, trading_pair)
print('设置的杠杆数不能超过', max_leverage)
if leverage >= max_leverage:
    print('设置杠杆倍数大于最大实际杠杆,程序退出')
    exit()
# 将各个标的的最大可用杠杆设置为最大值，及设置账户模式为全仓模式
set_leverage(exchange, coin_info, trading_pair)
# 获取交割、永续合约面值，即一张合约对应的币的数量
coin_info = get_future_value(exchange, coin_info, trading_pair)
# 获取相应永续合约的资金费率
funds_rate_list = get_funds_rate(exchange, coin_info['swap']['name'])
# 获取借币日利率
coin_info = obtain_interest_rate(exchange, long_or_short, coin_info, coin)
print(coin_info)
exit()

# =====自动循环建仓
execute_num = 0
while True:

    # 获取价格数据
    price_1 = exchange.fetchTicker(symbol=coin_info[trading_pair[0]]['name'])[coin_info[trading_pair[0]]['trade_price']]
    price_2 = exchange.fetchTicker(symbol=coin_info[trading_pair[1]]['name'])[coin_info[trading_pair[1]]['trade_price']]
    # 获取合约到期时间（根据config里面的future_date获取，所以即使套利标的中没有交割合约，也能获取时间）
    delivery_hours = get_delivery_by_day(future_date)

    # 计算价差
    spread = (price_2 / price_1) - 1
    print('标的1价格：%.4f，标的2价格：%.4f，价差：%.2f%%, 杠杆倍数: %s, 借币日利率为: %.2f%%, 合约到期剩余: %s小时，永续合约资金费率：%s' % (
        price_1, price_2, spread * 100, coin_info['lever_rate'], coin_info['spot']['interest_rate'] * 100,
        delivery_hours, funds_rate_list))

    # 判断价差是否满足要求
    if (long_or_short == 'long') & (spread < r_threshold_open):
        if_open_positions = True
    elif (long_or_short == 'short') & (spread > r_threshold_open):
        if_open_positions = True
    else:
        if_open_positions = False
        print('价差不符合目标，不开仓')
    # if_open_positions = True  # 强制开仓

    # 开仓
    if if_open_positions:
        print('价差符合目标，开仓')
        print('=' * 30, f'开始第{execute_num + 1}次开仓', '=' * 30)

        # 计算开仓币的数量
        coin_num = execute_amount * coin_info['lever_rate'] / max(price_1, price_2)
        coin_num = math.floor(coin_num / coin_info[trading_pair[1]]['face_value']) * coin_info[trading_pair[1]][
            'face_value']  # 向下取整

        if coin_num == 0:
            print('因为资金过少，开仓量为0，不开仓')
            exit()

        # 计算合约数量
        future_contract_num = coin_num / coin_info[trading_pair[1]]['face_value']
        # 根据手续费调整现货下单币数
        if long_or_short == 'short':
            coin_num = coin_num / (1 - coin_info['spot']['fee_rate'])

        # 打印计划下单信息
        print('交易计划：标的2开仓张数（或币数）：', future_contract_num, '标的1开仓张数（或币数）：', coin_num)

        # 标的1下单
        price = price_1 * coin_info[trading_pair[0]]['slippage']
        price = Decimal(price).quantize(Decimal(str(coin_info[trading_pair[0]]['price_accuracy'])))
        print('标的1下单价格：%s，标的1下单数量：%s，' % (price, coin_num))
        order_info1 = okex_place_order(exchange=exchange, symbol=coin_info[trading_pair[0]]['name'],
                                       buy_or_sell=coin_info[trading_pair[0]]['side'], price=price, amount=coin_num)

        # 标的2下单
        price = price_2 * coin_info[trading_pair[1]]['slippage']
        price = Decimal(price).quantize(Decimal(str(coin_info[trading_pair[1]]['price_accuracy'])))
        print('标的2下单价格：%s，标的2下单数量：%s，' % (price, future_contract_num))
        order_info2 = okex_place_order(exchange=exchange, symbol=coin_info[trading_pair[1]]['name'],
                                       buy_or_sell=coin_info[trading_pair[1]]['side'], price=price,
                                       amount=int(future_contract_num))

        # 计数
        execute_num += 1

        # # 获取当前持仓
        # pos_info = get_position_info(exchange, coin_info, trading_pair)  # 获取持仓信息
        # print(f'本次平仓完成, 剩余标的1的数量为: {pos_info[trading_pair[0]]["pos"]}, 剩余标的2的数量为: {pos_info[trading_pair[1]]["pos"]}')

    # 判断当前时间，19:18:58，minutes =0 second < 30
    # 每一小时更新一次借币利息
    coin_info = obtain_interest_rate(exchange, long_or_short, coin_info, coin)

    # ===循环结束
    print('*' * 30, '本次循环结束，暂停2秒', '*' * 30, '\n')
    time.sleep(2)

    if execute_num >= max_execute_num:
        print('达到最大下单次数，完成建仓计划，退出程序')
        break

"""
1. 当肉眼观测到价差较大时，或者留意策略分享会群消息，可以开始运行本程序。
2. 本程序开机之后就可以长期跑，直到完成建仓任务为止。可以睡前设置好，跑一夜。
3. 交易之后，要自己对着页面，去对比下每笔交易，看是否有问题。
"""
