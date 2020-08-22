from json import loads as json_loads
from json import dumps as json_dumps
from requests import get as r_get
from datetime import timedelta
from redis import Redis
from wowstash import config


class CoinInfo(object):
    def __init__(self):
        self.redis = Redis(host=config.REDIS_HOST, port=config.REDIS_PORT)

    def store_info(self, info):
        self.redis.setex(
            "info",
            timedelta(minutes=15),
            value=info
        )

    def get_info(self):
        info = self.redis.get("info")
        if info:
            return json_loads(info)
        else:
            data = {
                'localization': False,
                'tickers': False,
                'market_data': True,
                'community_data': False,
                'developer_data': False,
                'sparkline': False
            }
            headers = {'accept': 'application/json'}
            url = 'https://api.coingecko.com/api/v3/coins/wownero'
            r = r_get(url, headers=headers, data=data)
            info = {
                'genesis_date': r.json()['genesis_date'],
                'market_cap_rank': r.json()['market_cap_rank'],
                'current_price': r.json()['market_data']['current_price']['usd'],
                'market_cap': r.json()['market_data']['market_cap']['usd'],
                'market_cap_rank': r.json()['market_data']['market_cap_rank'],
                'total_volume': r.json()['market_data']['total_volume']['usd'],
                'last_updated': r.json()['last_updated']
            }
            self.store_info(json_dumps(info))
            return info

info = CoinInfo()