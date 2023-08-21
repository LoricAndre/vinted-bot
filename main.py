from pyVinted import Vinted
import discord
from discord.ext import tasks
import asyncio
from databases import Database
import os


class Query:
    def __init__(self, item):
        self.id, self.channel, self.url, self.last_item = item

    def __str__(self):
        return f"{self.id}: {self.channel}, {self.url}, {self.last_item}"

    async def run(self, vinted, db):
        items = []
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, vinted.items.search, self.url, 10, 1) # TODO pagination
        for item in res:
            if item.url == self.last_item:
                await db.execute(f'update queries set last_item = "{res[0].url}" where id = {self.id};')
                self.last_item = res[0].url
                return items
            items.append(Item(item, self.channel))
        await db.execute(f'update queries set last_item = "{res[0].url}" where id = {self.id};')
        self.last_item = res[0].url
        return items

class Item:
    def __init__(self, vinted_item, channel):
        self.id: int = vinted_item.id
        self.title = vinted_item.title
        self.photo = vinted_item.photo
        self.brand = vinted_item.brand_title
        self.price = vinted_item.price
        self.url = vinted_item.url
        self.currency = vinted_item.currency
        self.channel: int = channel

    def __str__(self):
        return f"""
**[{self.title}]({self.url})**
{self.price}{self.currency}
"""



        

class Client(discord.Client):
    def __init__(self, *args, intents=discord.Intents.default(), sqlite_path="./db.sqlite", **kwargs):
        super().__init__(*args, intents=intents, **kwargs)

        self.vinted = Vinted()

        self.db = Database(f"sqlite+aiosqlite://{sqlite_path}")
        # self.db_con = sqlite3.connect(sqlite_path)
        # self.db_cur = self.db_con.cursor()
        # tables = self.db_cur.execute("SELECT name FROM sqlite_schema WHERE type ='table' AND name NOT LIKE 'sqlite_%';")\
        #         .fetchall()
        # if not ("queries") in tables:
        #     self.db_cur.execute("create table if not exists queries(id primary key,channel text, url text, last_item text);")
        #     self.db_con.commit()
        # raw_queries = self.db_cur\
        #         .execute("select * from queries order by id asc;")
        # self.queries = [Query(q) for q in raw_queries]

    async def setup_hook(self):
        await self.db.connect()
        tables = await self.db.fetch_all(query="SELECT name FROM sqlite_schema WHERE type ='table' AND name NOT LIKE 'sqlite_%';")
        if not ("queries") in tables:
            await self.db.execute(query="create table if not exists queries(id primary key,channel integer, url text, last_item integer);")
        raw_queries = await self.db.fetch_all(query="select * from queries")
        self.queries = [Query(q) for q in raw_queries]
        self.query_loop.start()


    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        if message.content.startswith('!sub'):
            url = message.content.split(' ')[1]
            query = await self.register_query(channel=message.channel.id, url=url)
            await message.channel.send('New query added, fetching items...')
            query.run(self.vinted, self.db)
        elif message.content.startswith('!ls'):
            queries = await self.get_queries(message.channel.id)
            msg = "Queries in this channel:\n"
            for q in queries:
                msg += f"{q.id}: {q.url}\n"
            await message.channel.send(msg)
        elif message.content.startswith('!rm'):
            query_id = int(message.content.split(' ')[1])
            await self.delete_query(query_id, message.channel.id)
            await message.channel.send(f"Query {query_id} removed")
        # elif message.content.startswith("!!"):
        #     for item in await self.get_items():
        #         await message.channel.send(item)

    @tasks.loop(seconds=30)
    async def query_loop(self):
        print("Running queries...")
        for item in await self.get_items():
            channel = (
                self.get_channel(item.channel) 
                or 
                await self.fetch_channel(item.channel)
            )
            if channel is None:
                print(f"Channel with id {item.channel} not found, skipping query.")
            else:
                await channel.send(item)

    @query_loop.before_loop
    async def before_loop(self):
        await self.wait_until_ready()  # wait until the bot logs in

    async def register_query(self, url: str, channel: str):
        last_id = await self.db.fetch_one("select id from queries order by id desc limit 1;")
        if last_id is None:
            last_id = -1
        else:
            last_id = last_id[0]
        query = Query((last_id+1, channel, url, ""))
        await self.db.execute(f'insert into queries values({query.id}, "{query.channel}", "{query.url}","{query.last_item}");')
        self.queries.append(query)
        return query

    async def delete_query(self, query_id: int, channel: int):
        queries = await self.get_queries(channel)
        for q in queries:
            if q.id == query_id:
                self.queries.remove(q)
                await self.db.execute(f"delete from queries where id = {query_id};")
                return
        # self.queries = list(filter(lambda q: q.id != id, self.queries))

    async def get_queries(self, channel: int=0):
        if channel == 0:
            return self.queries
        else:
            # res = [q for q in self.queries if str(q.channel) == str(channel)]
            res = []
            for q in self.queries:
                if q.channel == channel:
                    res.append(q)
            return res
            # return list(filter(lambda q: str(q.channel) == str(channel), self.queries))

    async def get_items(self):
        res = []
        for q in self.queries:
            res += await q.run(self.vinted, self.db)
        return res


def main():
    c = Client()
    discord_token = os.environ.get("DISCORD_TOKEN", "")
    if discord_token == "":
        print("Please set the DISCORD_TOKEN environment variable")
        exit(1)
    c.run(discord_token)
    # c.register_query("https://www.vinted.fr/vetement?order=newest_first&price_to=60&currency=EUR", "")
    # for i in await c.get_items():
    #     print(i)
#
if __name__ == '__main__':
    main()
#     asyncio.run(main())
