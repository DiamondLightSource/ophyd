import argparse
import asyncio
import logging
from datetime import datetime, timedelta

from softioc import asyncio_dispatcher, builder, softioc
from softioc.builder import records


def options():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", default=1000, help="Number of records to create (1000)")
    parser.add_argument("-p", "--prefix", default="TEST", help="Record name prefix (TEST)")
    parser.add_argument("-r", "--rate", default=100.0, help="Update rate in Hz (100.0)")
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = options()
    args.number = int(args.number)
    args.rate = float(args.rate)

    # Create an asyncio dispatcher, the event loop is now running
    dispatcher = asyncio_dispatcher.AsyncioDispatcher()

    # Set the record prefix
    builder.SetDeviceName(args.prefix)

    with open("test.db", "w+") as f:
        # Create some records
        record_store = []
        for index in range(args.number):
            calc = records.calc('CALC{:05d}'.format(index), CALC="A+1", SCAN=".1 second")
            calc.INPA = builder.NP(calc)
            record_store.append(calc)
            calc.Print(f)


    # Boilerplate get the IOC started
    builder.LoadDatabase()
    softioc.iocInit(dispatcher)

#    # Start processes required to be run after iocInit
#    async def update():
#        start_time = datetime.now()
#        value = 0
#        while True:
#            for index in range(args.number):
#                record_store[index].set(value)
#            value += 1
#            sleep_time = (1.0 / args.rate) - (datetime.now() - start_time).total_seconds()
#            if sleep_time < 0.0:
#                logging.info("Caution - failing to keep up with rate: {}".format(args.rate))
#                sleep_time = 0.0
#            await asyncio.sleep(sleep_time)
#            start_time += timedelta(seconds=(1.0/args.rate))
#
#    dispatcher(update)

    # Finally leave the IOC running with an interactive shell.
    softioc.interactive_ioc(globals())


if __name__ == '__main__':
    main()
