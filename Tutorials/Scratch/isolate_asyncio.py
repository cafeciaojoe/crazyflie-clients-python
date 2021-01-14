import asyncio
import random

async def myCoroutine():
    process_time = random.randint(1,5)
    # await asyncio.sleep(process_time)

    print("coroutine has successfully completed after {} seconds".format(process_time))

def start_async_task(task):
    return asyncio.ensure_future(task)

start_async_task(myCoroutine())