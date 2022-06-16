#!/usr/bin/env python
# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord.ext import tasks
import json
import datetime
import requests

TOKEN = ""
PREFIX = ""
COMMERCE_API = ""
LOGGING_ID = 0

with open('config.json') as json_file:
    data = json.load(json_file)
    TOKEN = data["token"]
    PREFIX = data["prefix"]
    COMMERCE_API = data["coinbase_api_key"]
    LOGGING_ID = data["logging_channel"]


headers = {
    "X-CC-Version": "2018-03-22",
    "X-CC-Api-Key": COMMERCE_API
}

client = commands.Bot(command_prefix=PREFIX)
client.remove_command("help")


@tasks.loop(seconds=10)
async def check_tans():
    with open("subscriptions.json") as s:
        subscriptions = json.load(s)
    new_subs = dict()
    for user_id in subscriptions.keys():
        sub = subscriptions[user_id]

        today = datetime.datetime.today()
        end = datetime.datetime.strptime(sub["expires"], "%m/%d/%Y, %H:%M:%S")

        if today > end:
            guild = client.get_guild(sub["guild_id"])
            user = guild.get_member(int(user_id))
            role = discord.utils.get(guild.roles, id=sub["role_id"])
            await user.remove_roles(role)
            embed = discord.Embed(title="Expired", description="Your subscription expired. You can renew it anytime",
                                  color=discord.Color.red())
            await user.send(embed=embed)
            channel = client.get_channel(LOGGING_ID)
            await channel.send(user.name+"#"+str(user.discriminator)+" has has role "+role.name+" revoked")
            continue
        new_subs[user_id] = sub
    with open("subscriptions.json", "w") as s:
        json.dump(new_subs, s, indent=4)

    with open("transactions.json") as f:
        transactions = json.load(f)

    new_trans = dict()
    for charge_id in transactions.keys():
        r = requests.get("https://api.commerce.coinbase.com/charges/"+charge_id, headers=headers)
        if r.status_code != 200:
            print("=> Failed to check charge")
            continue
        json_data = r.json().get("data")
        for changelog in json_data.get("timeline"):
            if changelog["status"] == "COMPLETED":
                trans = transactions[charge_id]
                with open("products.json") as f:
                    products = json.load(f)
                for product_name in products.keys():
                    if product_name == trans["sub_name"]:
                        sub = products[product_name]
                        guild = client.get_guild(trans["guild_id"])
                        user = guild.get_member(trans["user_id"])
                        role = discord.utils.get(guild.roles, id=sub["role_id"])
                        await user.add_roles(role)
                        embed = discord.Embed(title="Transaction completed", description="Your role has been added to your account", color=discord.Color.green())
                        if sub["type"] == "subscription":

                            with open("subscriptions.json") as subf:
                                subs = json.load(subf)
                            today = datetime.datetime.today()
                            today = today + datetime.timedelta(weeks=4*sub["length"])

                            end = today.strftime("%m/%d/%Y, %H:%M:%S")

                            subs[str(trans["user_id"])] = {
                                "role_id": sub["role_id"],
                                "expires": end,
                                "guild_id": trans["guild_id"]
                            }
                            with open("subscriptions.json", "w") as subf:
                                json.dump(subs, subf, indent=4)

                            embed.add_field(name="Expires", value=end)

                        await user.send(embed=embed)
                        channel = client.get_channel(LOGGING_ID)
                        await channel.send("User "+user.name+"#"+user.discriminator+" has completed BTC purchase")
                        await channel.send(user.name + "#" + str(user.discriminator) + " has has role " + role.name + " added")
                        continue
                continue
            new_trans[charge_id] = trans

    with open("transactions.json", "w") as tw:
        json.dump(new_trans, tw, indent=4)


@client.command(name="add")
@commands.has_permissions(administrator=True)
async def add(ctx, sub_name, price : int, role : commands.RoleConverter):
    with open("products.json") as f:
        products = json.load(f)
    products[sub_name] = {
        "type": "one-time",
        "length": "u",
        "role_id": role.id,
        "price": price
    }
    with open("products.json", "w") as f:
        json.dump(products, f, indent=4)
    await ctx.send("You successfully added a product with the name: "+sub_name+" and the role: "+role.name)


@client.command(name="addsub")
@commands.has_permissions(administrator=True)
async def addsub(ctx, sub_name, length :int, price : int, role : commands.RoleConverter):
    with open("products.json") as f:
        products = json.load(f)
    products[sub_name] = {
        "type": "subscription",
        "length": length,
        "role_id": role.id,
        "price": price
    }
    with open("products.json", "w") as f:
        json.dump(products, f, indent=4)
    await ctx.send("You successfully added a subscription with the name: "+sub_name+" and the role: "+role.name)


@client.command(name="sendembed")
@commands.has_permissions(administrator=True)
async def sendembed(ctx, sub_name):
    with open("products.json") as f:
        products = json.load(f)
    for product_name in products.keys():
        if product_name.upper() == sub_name.upper():
            product = products[product_name]
            role = discord.utils.get(ctx.message.guild.roles, id=product["role_id"])
            embed = discord.Embed(title="Buy "+product_name, description="Buy this package by reacting to this message",
                                  color=discord.Color.green())
            embed.add_field(name="Role", value=role.name)
            embed.add_field(name="Price", value="$"+str(product["price"]))
            if product["type"] == "subscription":
                embed.add_field(name="Length", value=str(product["length"]) +" Month(s)")
            embed.set_footer(text="Use this command to buy this role: \""+PREFIX+"btc "+product_name+"\"")
            await ctx.send(embed=embed)
            await ctx.message.delete()

            return
    await ctx.send("This Product was not found")


@client.command(name="btc")
@commands.guild_only()
async def btc(ctx, sub_name):
    with open("products.json") as f:
        products = json.load(f)
    for product_name in products.keys():
        if product_name.upper() == sub_name.upper():
            product = products[product_name]
            post = {
                "name": product_name,
                "description": "Buy a role on "+ctx.message.guild.name,
                "local_price": {
                    "amount": product["price"],
                    "currency": "USD"
                },
                "pricing_type": "fixed_price",
                "metadata": {
                    "user_id": ctx.message.author.id,
                    "guild_id": ctx.message.guild.id,
                    "sub_name": product_name
                }
            }
            r = requests.post("https://api.commerce.coinbase.com/charges", json=post, headers=headers)
            if r.status_code != 201:
                embed = discord.Embed(title="Oops. Something went wrong", description="Please contact an administrator about this issue",
                                      color=discord.Color.red())
                await ctx.send(embed=embed)
                return
            json_r = r.json().get("data")
            embed = discord.Embed(title="Transaction started. ", description="Buy with crypto. After your payment is verified on Coinbase it can take up to 10min till your role is added",
                                  color=discord.Color.orange(), url=json_r.get("hosted_url"))
            embed.add_field(name="Transaction ID", value=json_r.get("code"))
            embed.add_field(name="Checkout url", value=json_r.get("hosted_url"), inline=False)
            embed.set_footer(text="Checkout using the given url. You will receive a DM as soon as your role is added")
            with open("transactions.json") as fc:
                charges = json.load(fc)
            charges[json_r.get("code")] = {
                "user_id": ctx.message.author.id,
                "guild_id": ctx.message.guild.id,
                "sub_name": product_name,
                "pending": 1
            }
            with open("transactions.json", "w") as fcw:
               json.dump(charges, fcw, indent=4)
            await ctx.message.author.send(embed=embed)
            channel = client.get_channel(LOGGING_ID)
            await channel.send("User " + ctx.message.author.name+"#"+ str(ctx.message.author.discriminator)+" initiated a btc pruchase")
            await ctx.message.delete()



@client.event
async def on_ready():
    printBanner()
    print("=> Command Prefix is " + PREFIX)
    print('=> Logged in as {0.user}'.format(client))
    game = discord.Game(name="Made by Nergon#4972")
    await client.change_presence(status=discord.Status.online, activity=game)
    check_tans.start()


# Helper Functions
def printBanner():
    print("-------------------------------------------")
    print("DISCORD BTC-DONATION BOT")
    print("-------------------------------------------")


client.run(TOKEN)
