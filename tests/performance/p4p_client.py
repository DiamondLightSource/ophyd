import argparse
import asyncio
import logging
import time

from p4p.client.thread import Context


# Create the monitor callback
def callback(value):
    pass

class PVMonitors(object):
    def __init__(self):
        self._subscriptions = None
        self._ctxt = Context('pva')

    def monitor_pv(self, args):
        self._subscriptions = []
        # Build the PV subscription list
        for pv_index in range(args.number):
            pv_name = '{}:AI{:05d}'.format(args.prefix, pv_index)
            for monitor_index in range(args.monitors):
                self._subscriptions.append(self._ctxt.monitor(pv_name, callback))

    def close_monitors(self):
        for sub in self._subscriptions:
            sub.close()


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", default=1, help="Number of PVs to monitor (1)")
    parser.add_argument("-p", "--prefix", default="TEST", help="Record name prefix (TEST)")
    parser.add_argument("-m", "--monitors", default=10, help="Number of monitors to place on each PV (10)")
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = options()
    args.number = int(args.number)
    args.monitors = int(args.monitors)

    mon = PVMonitors()
    mon.monitor_pv(args)
    # Wait for 30 seconds
    time.sleep(30.0)
    logging.info("Closing monitors")
    mon.close_monitors()


if __name__ == '__main__':
    main()
