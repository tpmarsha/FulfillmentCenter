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



sim_until = 86401*7
start_date = datetime.datetime(2020, 10, 22, 0, 0, tzinfo=None)
#===============================================================================
# Create list of order details

### Set varying order arrival rates by weekday and hour
### The factors are multiplicative, with the weekday modifying the base hourly rate

orderWeekdayFactors = {0: 2.50, 1: 3.33, 2: 1.42, 3: 2.5, 
                       4: 1.10, 5: 1.00, 6: 1.25}

orderHourFactors = {0: 30.56118, 
                    1: 54.01161, 
                    2: 106.26632, 
                    3: 207.85501, 
                    4: 215.03588, 
                    5: 213.78153, 
                    6: 111.61141, 
                    7: 45.72561, 
                    8: 27.29694, 
                    9: 21.61996, 
                    10: 15.47543, 
                    11: 18.15357, 
                    12: 13.54276, 
                    13: 13.46299, 
                    14: 15.28291, 
                    15: 18.14266, 
                    16: 13.57966, 
                    17: 18.0377, 
                    18: 15.60327, 
                    19: 11.97936, 
                    20: 10.75827, 
                    21: 12.09711, 
                    22: 15.45324, 
                    23: 21.59623}

# Poisson parameter for each item frequency in orders
mean_tshirt = 1.00
mean_hoodie = 0.50
mean_spants = 0.50
mean_sneaks = 0.25


# Generate list of random order times
start_date = datetime.datetime(2020, 10, 22, 0, 0, tzinfo=None)
orderGenClock = 0
orderTimes = []

while orderGenClock < sim_until:
    # Set order time parameter based on time of previous order
    orderDateTime = start_date + datetime.timedelta(seconds=orderGenClock)
    orderTimeMean = orderWeekdayFactors[orderDateTime.weekday()] * orderHourFactors[orderDateTime.hour]
    
    # Generate new order time based on current order time parameter
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
print(f'processed {tshirt_tot} tshirt')
print(f'processed {hoodie_tot} hoodie')
print(f'processed {spants_tot} spants')
print(f'processed {sneaks_tot} sneaks')
with open('orderlog.txt', 'w') as f:
    print(orders, file=f)