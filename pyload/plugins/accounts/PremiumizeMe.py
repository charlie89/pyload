from pyload.plugins.MultiHoster import MultiHoster
from pyload.utils import json_loads


class PremiumizeMe(MultiHoster):
    __name__ = "PremiumizeMe"
    __version__ = "0.11"
    __type__ = "account"
    __description__ = """Premiumize.me account plugin"""
    __author_name__ = "Florian Franzen"
    __author_mail__ = "FlorianFranzen@gmail.com"

    def loadAccountInfo(self, user, req):
        # Get user data from premiumize.me
        status = self.getAccountStatus(user, req)
        self.logDebug(status)

        # Parse account info
        account_info = {"validuntil": float(status['result']['expires']),
                        "trafficleft": max(0, status['result']['trafficleft_bytes'] / 1024)}

        if status['result']['type'] == 'free':
            account_info['premium'] = False

        return account_info

    def login(self, user, data, req):
        # Get user data from premiumize.me
        status = self.getAccountStatus(user, req)

        # Check if user and password are valid
        if status['status'] != 200:
            self.wrongPassword()

    def getAccountStatus(self, user, req):
        # Use premiumize.me API v1 (see https://secure.premiumize.me/?show=api)
        # to retrieve account info and return the parsed json answer
        answer = req.load(
            "https://api.premiumize.me/pm-api/v1.php?method=accountstatus&params[login]=%s&params[pass]=%s" % (
            user, self.accounts[user]['password']))
        return json_loads(answer)

    def loadHosterList(self, req):
        # Get supported hosters list from premiumize.me using the
        # json API v1 (see https://secure.premiumize.me/?show=api)
        answer = req.load(
            "https://api.premiumize.me/pm-api/v1.php?method=hosterlist&params[login]=%s&params[pass]=%s" % (
            self.loginname, self.password))
        data = json_loads(answer)

        # If account is not valid thera are no hosters available
        if data['status'] != 200:
            return []

        # Extract hosters from json file
        return data['result']['hosterlist']
