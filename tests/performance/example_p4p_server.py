import argparse
import asyncio
import logging
from datetime import datetime, timedelta

from p4p.nt import NTScalar
from p4p.server import Server
from p4p.server.asyncio import SharedPV


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", default=1000, help="Number of records to create (1000)")
    parser.add_argument("-p", "--prefix", default="TEST", help="Record name prefix (TEST)")
    parser.add_argument("-r", "--rate", default=100.0, help="Update rate in Hz (100.0)")
    args = parser.parse_args()
    return args


# Start processes required to be run after iocInit
async def update(args, record_store):
    start_time = datetime.now()
    value = 0
    while True:
        for index in range(args.number):
            record_store['{}{:05d}'.format(args.prefix, index)].post(value)
        value += 1
        sleep_time = (1.0 / args.rate) - (datetime.now() - start_time).total_seconds()
        if sleep_time < 0.0:
            logging.info("Caution - failing to keep up with rate: {}".format(args.rate))
            sleep_time = 0.0
        await asyncio.sleep(sleep_time)
        start_time += timedelta(seconds=(1.0/args.rate))


async def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = options()
    args.number = int(args.number)
    args.rate = float(args.rate)

    # Create some records
    record_store = {}
    for index in range(args.number):
        record_store['{}{:05d}'.format(args.prefix, index)] = SharedPV(nt=NTScalar('i'), value=0)
        record_store['{}{:05d}'.format(args.prefix, index)].open(0)

    logging.info("Records: {}".format(record_store))

    S = Server(providers=[record_store])
    await update(args, record_store)
        

if __name__ == '__main__':
    asyncio.run(main())
