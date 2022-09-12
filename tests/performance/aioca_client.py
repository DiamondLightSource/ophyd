import argparse
import asyncio
import logging
import time

from aioca import FORMAT_TIME, caget, camonitor, caput, run


# Create the monitor callback
def callback(value, index):
    pass

class PVMonitors(object):
    def __init__(self):
        self._subscriptions = None

    async def monitor_pv(self, args):
        sub_list = []
        # Build the PV subscription list
        for pv_index in range(args.number):
            pv_name = '{}{:05d}'.format(args.prefix, pv_index)
            for monitor_index in range(args.monitors):
                sub_list.append(pv_name)
        
        # Now set up the monitors
        logging.info("PV list: {}".format(sub_list))
        self._subscriptions = camonitor(sub_list, callback, format=FORMAT_TIME)


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", default=1, help="Number of PVs to monitor (1)")
    parser.add_argument("-p", "--prefix", default="TEST:AI", help="Record name prefix (TEST:AI)")
    parser.add_argument("-m", "--monitors", default=10, help="Number of monitors to place on each PV (10)")
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = options()
    args.number = int(args.number)
    args.monitors = int(args.monitors)

    mon = PVMonitors()
    # Now run the camonitor process until interrupted by Ctrl-C.
    run(mon.monitor_pv(args), forever=True)


if __name__ == '__main__':
    main()
