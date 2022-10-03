import argparse
import asyncio
import logging
import time

from caproto.threading.client import Context

# Create the monitor callback
def callback(sub, value):
    # Assign value
    item = value
    #logging.info("Value: {} {}".format(sub, value))

class PVMonitors(object):
    def __init__(self):
        self._subscriptions = []
        self._ctx = Context()

    def monitor_pv(self, args):
        sub_list = []
        # Build the PV subscription list
        pv_names = []
        for pv_index in range(args.number):
            pv_name = '{}{:05d}'.format(args.prefix, pv_index)
            pvs = self._ctx.get_pvs(pv_name)
            logging.info("PV {}".format(pv_name))
            pv = pvs[0]
            logging.info("PV {}".format(pv.read()))

            for monitor_index in range(args.monitors):
                sub = pv.subscribe()
                sub.add_callback(callback)
                self._subscriptions.append(sub)


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
    mon.monitor_pv(args)
    while True:
        time.sleep(1.0)


if __name__ == '__main__':
    main()
