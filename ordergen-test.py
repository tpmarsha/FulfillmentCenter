############################
# Order generation testing #
############################


### Import packages from full simulation to ensure I don't have incompatabilities during testing

import enum
import time
import math
import simpy
import random
import datetime
import pandas as pd


# Add numpy package to get Poisson and exponential random variables
import numpy as np



sim_until = 1000
start_date = datetime.datetime(2020, 10, 22, 0, 0, tzinfo=None)
#===============================================================================
# Create list of order details

# TODO: Add exponential order time generation. Currently set to every 30 sec - jculbert

# Poisson parameter for each item frequency in orders
mean_tshirt = 1.00
mean_hoodie = 0.50
mean_spants = 0.50
mean_sneaks = 0.25

orderGenClock = 0

# TODO: Add varying exponential means by hour and weekday - jculbert
# Current code generates exponential order arrivals with fixed mean
orderTimeMean = 30 

# Generate list of random order times
orderTimes = []

while orderGenClock < sim_until:
    orderGenClock = orderGenClock + np.random.exponential(orderTimeMean)
    orderTimes.append(orderGenClock)
print(f'generated {len(orderTimes)} orders')

orderTimes.reverse() # Reverse list so we pop off the first orders first

# Generate a list of candidate orders. Needs to be filtered to remove blanks
# Filtering out blanks before order time generation to preserve statistical properties
candidate_orders = []
for i in range(len(orderTimes)*2):
    candidate_order = np.random.poisson([mean_tshirt, mean_hoodie, mean_spants, mean_sneaks])
    if candidate_order.max() > 0:
        candidate_orders.append(candidate_order)

# Populate orders with entries from the candidate order list
orders = {}
for i in range(len(orderTimes)):
    next_order = candidate_orders.pop()
    orders[i] = {
        'OrderTimeInSec': orderTimes.pop(), 
        'QtyShirt': next_order[0], 
        'QtyHoodie': next_order[1], 
        'QtySweatpants': next_order[2], 
        'QtySneakers': next_order[3]
    }

tshirt_tot = 0
hoodie_tot = 0
spants_tot = 0
sneaks_tot = 0

for i in orders:
    tshirt_tot += orders[i]['QtyShirt']
    hoodie_tot += orders[i]['QtyHoodie']
    spants_tot += orders[i]['QtySweatpants']
    sneaks_tot += orders[i]['QtySneakers']


print(f'processed {len(orders)} orders')
print(f'sold {tshirt_tot} tshirt')
print(f'sold {hoodie_tot} hoodie')
print(f'sold {spants_tot} spants')
print(f'sold {sneaks_tot} sneaks')
with open('orderlog.txt', 'w') as f:
    print(orders, file=f)