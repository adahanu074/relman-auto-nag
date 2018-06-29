# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from dateutil.relativedelta import relativedelta
from jinja2 import Environment, FileSystemLoader
import json
from libmozdata.bugzilla import Bugzilla
from libmozdata import utils as lmdutils
from auto_nag.bugzilla.utils import get_config_path
from auto_nag import mail, utils


# https://bugzilla.mozilla.org/buglist.cgi?keywords=topcrash%2C%20&keywords_type=allwords&bug_severity=major&bug_severity=normal&bug_severity=minor&bug_severity=trivial&bug_severity=enhancement&resolution=---&query_format=advanced
def get_bz_params(date):
    date = lmdutils.get_date_ymd(date)
    lookup = utils.get_config('has_reg_range', 'days_lookup', 7)
    start_date = date - relativedelta(days=lookup)
    end_date = date + relativedelta(days=1)
    fields = ['id']
    params = {'include_fields': fields,
              'resolution': ['---'],
              "bug_severity": ["major", "normal", "minor", "trivial", "enhancement"],
              'keywords': 'topcrash',
              'keywords_type': 'allwords'
              }

    return params


def get_bugs(date='today'):
    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        data.append(bug['id'])

    bugids = []
    Bugzilla(get_bz_params(date),
             bughandler=bug_handler,
             bugdata=bugids,
             timeout=TIMEOUT).get_data().wait()

    return sorted(bugids)


def autofix(bugs):
    bugs = list(map(str, bugs))
    Bugzilla(bugs).put({
        'keywords': {
            'add': ['regression']
            }
        })

    return bugs


def get_login_info():
    with open(get_config_path(), 'r') as In:
        return json.load(In)


def get_email(bztoken, date, dryrun):
    Bugzilla.TOKEN = bztoken
    bugids = get_bugs(date=date)
    if not dryrun:
        bugids = autofix(bugids)
    if bugids:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('topcrash_bas_severity.html')
        body = template.render(date=date,
                               bugids=bugids)
        title = '[autonag] Bugs with topcrash keyword but incorrect severity {}'.format(date)
        return title, body
    return None, None


def send_email(date='today', dryrun=False):
    login_info = get_login_info()
    date = lmdutils.get_date(date)
    title, body = get_email(login_info['bz_api_key'], date, dryrun)
    if title:
        mail.send(login_info['ldap_username'],
                  utils.get_config('has_reg_range', 'receivers', ['sylvestre@mozilla.com']),
                  title, body,
                  html=True, login=login_info, dryrun=dryrun)
    else:
        print('HAS_REG_RANGE: No data for {}'.format(date))


if __name__ == '__main__':
    description = 'Get the top crashes bug without a proper severity'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-d', '--dryrun', dest='dryrun',
                        action='store_true', default=False,
                        help='Just do the query, and print emails to console without emailing anyone') # NOQA
    parser.add_argument('-D', '--date', dest='date',
                        action='store', default='today',
                        help='Date for the query')
    args = parser.parse_args()
    send_email(date=args.date, dryrun=args.dryrun)
