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



sim_until = 100000
#===============================================================================
# Create list of order details

# TODO: Add exponential order time generation. Currently set to every 30 sec - jculbert

# Poisson parameter for each item frequency in orders
mean_tshirt = 1.00
mean_hoodie = 0.50
mean_spants = 0.50
mean_sneaks = 0.25

# Generate a list of candidate orders. Needs to be filtered to remove blanks
# Filtering out blanks before order time generation to preserve statistical properties
candidate_orders = []
for i in range(divmod(sim_until,20)[0]):
    candidate_order = np.random.poisson([mean_tshirt, mean_hoodie, mean_spants, mean_sneaks])
    if candidate_order.max() > 0:
        candidate_orders.append(candidate_order)

# Populate orders with entries from the candidate order list
orders = {}
for i in range(1,divmod(sim_until,30)[0]):
    next_order = candidate_orders.pop()
    orders[i] = {
        'OrderTimeInSec': 30*i, 
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