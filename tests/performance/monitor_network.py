import argparse
import logging
import time

import psutil


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interface", default="enp1s0", help="Ethernet interface to monitor (enp1s0)")
    parser.add_argument("-t", "--time", default=10.0, help="Seconds to monitor (10.0)")
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = options()
    time_delay = int(args.time)

    dummy_data = psutil.net_io_counters(pernic=True)
    network1 = psutil.net_io_counters(pernic=True)
    #time.sleep(1.0)
    #logging.info("{}".format(network1))
    network1 = psutil.net_io_counters(pernic=True)

    index = 0
    while index < time_delay:
        index += 1
        network1 = psutil.net_io_counters(pernic=True)
        time.sleep(1.0)
        network2 = psutil.net_io_counters(pernic=True)
            #logging.info("{}".format(network2))

#        logging.info("{}".format(network1[args.interface]))
#        logging.info("{}".format(network2[args.interface]))
        if_start = network1[args.interface]
        if_end = network2[args.interface]
        total_recv = if_end.bytes_recv - if_start.bytes_recv
        av_recv = total_recv / 1024
        total_sent = if_end.bytes_sent - if_start.bytes_sent
        av_sent = total_sent / 1024

        logging.info("KBytes sent per second: {}".format(av_sent))
        logging.info("KBytes recv per second: {}".format(av_recv))


if __name__ == '__main__':
    main()
