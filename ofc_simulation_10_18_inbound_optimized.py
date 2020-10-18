################################################################################
## Description: Order Fulfillment Center Simulation program based on 
## pre-determined conceptual model. Simulation policy decisions may be set in 
## the "Set Policy Decisions" section. Do to the number of processes that may 
## be generated (depending on polcies set), this program may take upward of 10 
## minutes per week to run.
################################################################################
## Course:46893-M1 Operations and Supply Chain Analytics
## Professor: Joseph Xu
## Program: MSBA, CMU - Tepper School of Business
################################################################################
## Authors: Tim Marshall, Jonathan Culbert, George Matthew, Thao Spraggins
## Date: 10-17-2020
## Version: 1.0.0
## Email: tpmarsha@tepper.cmu.edu, TODO: email addresses
## Status: Final Submission
################################################################################

import os
import enum
import time
import math
import simpy
import random
import datetime
import numpy as np
import pandas as pd

################################################################################
## Class Definitions                                   
################################################################################

"""
CustomerOrderStatus enum values represent the state of orders as they proceed
through the fulfillment center operations flow.
"""
class CustomerOrderStatus(enum.Enum):
    UNPROCESSED     = 1,
    ARRIVED         = 2,
    FILLED          = 3,
    WAITING_TO_PACK = 4,
    SHIPPED         = 5,
    DISCARDED       = 6,
    CANCELLED       = 7

"""
CustomerOrder objects represent an order processed by the fulfillment center.
"""
class CustomerOrder:
    def __init__(self, env, warehouse, idx, order_details):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            idx (int): unique identifier index
            order_details (dict): defines order requirements
        """
        # order will be cancelled when age hits order expiration (72 hours)
        self.ORDER_EXPIRATION = 72*60*60

        # order detail properties
        self.idx = idx
        self.arrival_time = order_details['OrderTimeInSec']
        self.qty_tshirt = order_details['QtyShirt']
        self.qty_hoodie = order_details['QtyHoodie']
        self.qty_spants = order_details['QtySweatpants']
        self.qty_sneaks = order_details['QtySneakers']

        # track items allocated to this order from storage
        self.allocated_tshirt = 0
        self.allocated_hoodie = 0
        self.allocated_spants = 0
        self.allocated_sneaks = 0

        # for testing, to ensure order arrives on time as expected
        self.time_to_arrive = 0

        # order status represents state of the order
        self.status = CustomerOrderStatus.UNPROCESSED
    
    def get_lost_sales_penalty(self, env, warehouse):
        """ Calculate and return the lost sales penalty for this order. 
        Disregards order status.

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility

        Return:
            float: lost sales penalty for this order
        """
        return (
            self.qty_tshirt*warehouse.unit_lost_sales_penalty['tshirt'] +
            self.qty_hoodie*warehouse.unit_lost_sales_penalty['hoodie'] +
            self.qty_spants*warehouse.unit_lost_sales_penalty['spants'] +
            self.qty_sneaks*warehouse.unit_lost_sales_penalty['sneaks']
        )

    def get_gross_profit(self, env, warehouse):
        """ Calculate and return the gross profit for this order. Disregards order 
        status.

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility

        Return:
            float: gross profit for this order
        """
        return (
            self.qty_tshirt*warehouse.unit_gross_profit['tshirt'] +
            self.qty_hoodie*warehouse.unit_gross_profit['hoodie'] +
            self.qty_spants*warehouse.unit_gross_profit['spants'] +
            self.qty_sneaks*warehouse.unit_gross_profit['sneaks']
        )

    def check_if_filled(self, env):
        """ Check if order has been allotted the full amount of items requested.

        Args:
            env (simpy.Environment): simulation environment
        Return:
            bool: 1 if order is filled, otherwise 0
        """
        if (self.allocated_tshirt == self.qty_tshirt and
            self.allocated_hoodie == self.qty_hoodie and
            self.allocated_spants == self.qty_spants and
            self.allocated_sneaks == self.qty_sneaks):
            return 1
        return 0

    def get_age(self, env):
        """ Calculate and return age of the order.

        Return:
            int: age of order in seconds
        """
        return env.now - self.arrival_time

    def log_processed_order(self, env, warehouse):
        """ Log details of this order to warehouse processed orders DataFrame. 
        Function does not actually take into account the status of the order.

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
        """
        warehouse.log_processed_orders = warehouse.log_processed_orders.append({
        'idx':self.idx,
        'status':self.status,
        'time_to_process':self.get_age(env),
        'arrival_time':self.arrival_time,
        'time_to_arrive':self.time_to_arrive,
        'time_to_complete':env.now,
        'qty_tshirt':self.qty_tshirt,
        'qty_hoodie':self.qty_hoodie,
        'qty_spants':self.qty_spants,
        'qty_sneaks':self.qty_sneaks,
        'allocated_tshirt':self.allocated_tshirt,
        'allocated_hoodie':self.allocated_hoodie, 
        'allocated_spants':self.allocated_spants,
        'allocated_sneaks':self.allocated_sneaks}, ignore_index=True)
        
"""
PackingStation objects represent packing stations installed at the fulfillment
center. Each packing station installed costs $50,000 for a 52 week period. 
Installed packing stations remain fixed throughout the simulation.
"""
class PackingStation:
    def __init__(self, env, name):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            name (str): arbitrary value used to identify packing station
        """
        self.name = name
        # manage packer stationed at packing station with request() requests
        self.slots = simpy.Resource(env, capacity=1)
        # manage order queue with get() and put() requests
        self.queue = simpy.Store(env)

"""
InventoryBin objects are made up of simpy.Containers for each product type. 
"""
class InventoryBin:
    def __init__(self, env, bin_location, initial_qtys):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            bin_location (int): ordered location identifier
            initial_qtys (dict): initial quantities of each product type
        """
        self.location = bin_location
        self.avail_tshirt = simpy.Container(env, init=initial_qtys['tshirt'])
        self.avail_hoodie = simpy.Container(env, init=initial_qtys['hoodie'])
        self.avail_spants = simpy.Container(env, init=initial_qtys['spants'])
        self.avail_sneaks = simpy.Container(env, init=initial_qtys['sneaks'])

    def get_product_container(self, product):
        """ Helper function for easy access to different product containers.

        Args:
            product (string): the type of product whose container is requested
        Return:
            simpy.Container: the container associated with the requested product
        """
        if product == 'tshirt':
            return self.avail_tshirt
        if product == 'hoodie':
            return self.avail_hoodie
        if product == 'spants':
            return self.avail_spants
        if product == 'sneaks':
            return self.avail_sneaks

    def get_max_work_product_type(self, env, warehouse):
        """ Calculate and return product with most work remaining in the bin.

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
        """
        remaining_work = {
            'tshirt':self.avail_tshirt.level*warehouse.unit_weight['tshirt'],
            'hoodie':self.avail_hoodie.level*warehouse.unit_weight['hoodie'],
            'spants':self.avail_spants.level*warehouse.unit_weight['spants'],
            'sneaks':self.avail_sneaks.level*warehouse.unit_weight['sneaks']
        }
        # establish list of products with max work remaining
        max_work = max(remaining_work.values()) 
        max_products = [
            key for key in remaining_work if remaining_work[key] == max_work
        ]
        if max_work == 0:
            # no products have any work left
            return {'product_type': 'None', 'work_remaining':0}
        else:
            # randomly select from products with matching max work remaining
            i = random.randint(0,len(max_products)-1)
            product = max_products[i]
            return {'product_type': product, 'work_remaining':max_work}

"""
DesignatedInventoryStorage objects define the functionality of a designated
storage policy. Each inventory storage area only carries one type of product.
For convenience we designate area 1 to tshirts, area 2 to hoodies, area 3 to
sweatpants (aka spants), and area 4 to sneakers (aka sneaks).
"""
class DesignatedInventoryStorage:
    def __init__(self, env, initial_qtys):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            initial_qtys (dict): initial quantities of each product type
        """
        self.initial_qtys = initial_qtys
        # setup designated inventory bins, one for each product type
        # set other quantities to zero
        self.bin1 = InventoryBin(env, 1, {
            'tshirt':initial_qtys['tshirt'],
            'hoodie':0,
            'spants':0,
            'sneaks':0})
        self.bin2 = InventoryBin(env, 2, {
            'tshirt':0,
            'hoodie':initial_qtys['hoodie'],
            'spants':0,
            'sneaks':0})
        self.bin3 = InventoryBin(env, 3, {
            'tshirt':0,
            'hoodie':0,
            'spants':initial_qtys['spants'],
            'sneaks':0})
        self.bin4 = InventoryBin(env, 4, {
            'tshirt':0,
            'hoodie':0,
            'spants':0,
            'sneaks':initial_qtys['sneaks']})

    def check_inventory(self, env, order):
        """ Check inventory storage to ensure enough inventory is available to
        fulfill an order.

        Args:
            env (simpy.Environment): simulation environment
            order (CustomerOrder): order to check inventory for
        Return:
            bool: 1 if there is enough inventory to fulfill order, otherwise 0
        """
        if order.qty_tshirt > self.bin1.avail_tshirt.level:
            return 0
        if order.qty_hoodie > self.bin2.avail_hoodie.level:
            return 0
        if order.qty_spants > self.bin3.avail_spants.level:
            return 0
        if order.qty_sneaks > self.bin4.avail_sneaks.level:
            return 0
        return 1 

    def pickup_inventory(self, env, warehouse, order, name):
        """ Pickup inventory process generator for designated inventory policy. 
        During lifetime will generate get() request events from inventory 
        containers.
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            order (CustomerOrder): order to pickup inventory for
            name (str): name to identify associated picker
        """
        # track path of the picker between bins
        bin_path = []
        # repeat for each product type:
        # 1. allocate products to order to avoid collision with other pickers
        # 2. generate get() requests for associated product containers
        # 3. update picker path
        if order.qty_tshirt > 0:
            order.allocated_tshirt = order.allocated_tshirt + order.qty_tshirt
            yield self.bin1.avail_tshirt.get(order.qty_tshirt)
            bin_path.append(self.bin1.location)
        if order.qty_hoodie > 0:
            order.allocated_hoodie = order.allocated_hoodie + order.qty_hoodie
            yield self.bin2.avail_hoodie.get(order.qty_hoodie)
            bin_path.append(self.bin2.location)
        if order.qty_spants > 0:
            order.allocated_spants = order.allocated_spants + order.qty_spants
            yield self.bin3.avail_spants.get(order.qty_spants)
            bin_path.append(self.bin3.location)
        if order.qty_sneaks > 0:
            order.allocated_sneaks = order.allocated_sneaks + order.qty_sneaks
            yield self.bin4.avail_sneaks.get(order.qty_sneaks)
            bin_path.append(self.bin4.location)
        # since bins are accessed in order, start bin is first, end bin is last
        start_bin_location = bin_path[0]
        end_bin_location = bin_path[len(bin_path)-1]
        # calculate time for picker to pickup all items in order
        pickup_time = (
            # time to travel from picking station to first bin
            120 + 
            # time to pick up indvidual items
            order.qty_tshirt*10 + 
            order.qty_hoodie*10 + 
            order.qty_spants*10 + 
            order.qty_sneaks*10 + 
            # time to travel between bins
            (end_bin_location - start_bin_location)*60 + 
            120 # time to travel back to picking station
        )
        # simulate time to pickup items then continue
        yield env.timeout(pickup_time)
        # update order status
        if order.status != CustomerOrderStatus.CANCELLED:
            order.status = CustomerOrderStatus.FILLED

    def stow_inventory(self, env, warehouse, product_type, amount, name):
        """ Stow inventory process generator for designated inventory policy. 
        During lifetime will generate put() request events from stowing 
        inventory in containers.
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            product_type (str): product type to stow
            amount (int): number of product units to stow
            name (str): name to identify associated stower
        """
        # simulate travel time from inbound parking to storage then continue
        yield env.timeout(120)
        # track total time to stow items
        total_stow_time = 120
        # place units into storage one at a time until none remain
        while amount > 0:
            # simulate wait time to stow one unit of a product
            yield env.timeout(10) 
            # update total stow time
            total_stow_time = total_stow_time + 10
            # stow one unit of the product with put() request
            if product_type == 'tshirt':
                self.bin1.get_product_container(product_type).put(1)
            if product_type == 'hoodie':
                self.bin2.get_product_container(product_type).put(1)
            if product_type == 'spants':
                self.bin3.get_product_container(product_type).put(1)
            if product_type == 'sneaks':
                self.bin4.get_product_container(product_type).put(1)
            amount = amount - 1
        # simulate travel time to return to inbound parking
        yield env.timeout(120) 
        # update total stow time
        total_stow_time = total_stow_time + 120

"""
RandomInventoryStorage objects define the functionality of a random
storage policy. Inventory for all product types is evenly distributed between
all four areas (bins). If the number of units stored initially, or by a stower, 
is not evenly divisible by 4, then the number of units stowed in each area is 
rounded down, with the remainder being stowed in area 4.
"""
class RandomInventoryStorage:
    def __init__(self, env, initial_qtys):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            initial_qtys (dict): initial quantities of each product type
        """
        # calculate product quantity splits with remainders
        tshirt_split, tshirt_remain = divmod(initial_qtys['tshirt'],4)
        hoodie_split, hoodie_remain = divmod(initial_qtys['hoodie'],4)
        spants_split, spants_remain = divmod(initial_qtys['spants'],4)
        sneaks_split, sneaks_remain = divmod(initial_qtys['sneaks'],4)
        # setup splt bins, remaining inventory from uneven splits goes to bin 4
        self.bin1 = InventoryBin(env, 1, {
            'tshirt':tshirt_split,
            'hoodie':hoodie_split,
            'spants':spants_split,
            'sneaks':sneaks_split})
        self.bin2 = InventoryBin(env, 2, {
            'tshirt':tshirt_split,
            'hoodie':hoodie_split,
            'spants':spants_split,
            'sneaks':sneaks_split})
        self.bin3 = InventoryBin(env, 3, {
            'tshirt':tshirt_split,
            'hoodie':hoodie_split,
            'spants':spants_split,
            'sneaks':sneaks_split})
        self.bin4 = InventoryBin(env, 4, {
            'tshirt':tshirt_split + tshirt_remain,
            'hoodie':hoodie_split + hoodie_remain,
            'spants':spants_split + spants_remain,
            'sneaks':sneaks_split + sneaks_remain})

    def check_inventory(self, env, order):
        """ Check inventory storage to ensure enough inventory is available to
        fulfill an order.

        Args:
            env (simpy.Environment): simulation environment
            order (CustomerOrder): order to check inventory for
        Return:
            bool: 1 if there is enough inventory to fulfill order, otherwise 0
        """
        if order.qty_tshirt > (
            self.bin1.avail_tshirt.level + self.bin1.avail_tshirt.level +
            self.bin3.avail_tshirt.level + self.bin4.avail_tshirt.level):
            return 0
        if order.qty_hoodie > (
            self.bin1.avail_hoodie.level + self.bin1.avail_hoodie.level +
            self.bin3.avail_hoodie.level + self.bin4.avail_hoodie.level):
            return 0
        if order.qty_spants > (
            self.bin1.avail_spants.level + self.bin1.avail_spants.level +
            self.bin3.avail_spants.level + self.bin4.avail_spants.level):
            return 0
        if order.qty_sneaks > (
            self.bin1.avail_sneaks.level + self.bin1.avail_sneaks.level +
            self.bin3.avail_sneaks.level + self.bin4.avail_sneaks.level):
            return 0
        return 1 

    def pickup_inventory(self, env, warehouse, order, name):
        """ Pickup inventory process generator for random inventory policy. 
        During lifetime will generate get() request events from inventory 
        containers.
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            order (CustomerOrder): order to pickup inventory for
            name (str): name to identify associated picker
        """
        # track number of moves between bins, start at -1 to handle initial bin
        bin_moves = -1

        # randomly select initial bin
        target_bin = random.randint(1,4)

        # until the order is fill the picker follows the pattern:
        # 1. pickup inventory from target bin that is available
        # 2. if there is not enough inventory in the target bin, randomly select
        #    an adjacent bin as the new target bin
        # 3. repeat 1-2
        while not order.check_if_filled(env):
            # set current bin to be bin object associated with the target bin id
            if(target_bin == 1): current_bin = self.bin1 
            if(target_bin == 2): current_bin = self.bin2 
            if(target_bin == 3): current_bin = self.bin3
            if(target_bin == 4): current_bin = self.bin4

            # calculate num of tshirts to get from current bin
            amount_tshirt = order.qty_tshirt - order.allocated_tshirt
            tshirt_get_amount = 0
            tshirt_level = current_bin.avail_tshirt.level
            if amount_tshirt > 0 and tshirt_level > 0:
                tshirt_get_amount = min(tshirt_level, amount_tshirt)
                # allocate tshirts to the customer order
                order.allocated_tshirt += tshirt_get_amount

            # calculate num of hoodies to get from current bin
            amount_hoodie = order.qty_hoodie - order.allocated_hoodie
            hoodie_get_amount = 0
            hoodie_level = current_bin.avail_hoodie.level
            if amount_hoodie > 0 and hoodie_level > 0:
                hoodie_get_amount = min(hoodie_level, amount_hoodie)
                # allocate hoodies to the customer order
                order.allocated_hoodie += hoodie_get_amount

            # calculate num of spants to get from current bin
            amount_spants = order.qty_spants - order.allocated_spants
            spants_get_amount = 0
            spants_level = current_bin.avail_spants.level
            if amount_spants > 0 and spants_level > 0:
                spants_get_amount = min(spants_level, amount_spants)
                # allocate spants to the customer order
                order.allocated_spants += spants_get_amount

            # calculate num of sneaks to get from current bin
            amount_sneaks = order.qty_sneaks - order.allocated_sneaks
            sneaks_get_amount = 0
            sneaks_level = current_bin.avail_sneaks.level
            if amount_sneaks > 0 and sneaks_level > 0:
                sneaks_get_amount = min(sneaks_level, amount_sneaks)
                # allocate sneaks to the customer order
                order.allocated_sneaks += sneaks_get_amount
            
            # yield get() requests events to get inventory, then continue
            if tshirt_get_amount > 0:
                yield current_bin.avail_tshirt.get(tshirt_get_amount)
            if hoodie_get_amount > 0:
                yield current_bin.avail_hoodie.get(hoodie_get_amount)
            if spants_get_amount > 0:
                yield current_bin.avail_spants.get(spants_get_amount)
            if sneaks_get_amount > 0:
                yield current_bin.avail_sneaks.get(sneaks_get_amount)
            
            # select random adjacent bin, 
            if   target_bin == 1: target_bin = 2
            elif target_bin == 4: target_bin = 3
            else:
                left_bin  = max(1, target_bin-1) # if 2 then 1, if 3 then 2
                right_bin = min(4, target_bin+1) # if 2 then 3, if 3 then 4
                target_bin = random.randint(left_bin, right_bin)

            # increment number of moves between bins
            bin_moves = bin_moves + 1

        # calculate how long it takes for this pickup
        pickup_time = (
            # time to travel from picking station to first bin
            120 + 
            # time to pick up individual items
            order.qty_tshirt*10 +
            order.qty_hoodie*10 +
            order.qty_spants*10 +
            order.qty_sneaks*10 +
            # time to travel between bins
            bin_moves*60 + 
            # time to travel back to picking station
            120
        )
        # simulate time to pickup items then continue
        yield env.timeout(pickup_time)
        # update order status
        if order.status != CustomerOrderStatus.CANCELLED:
            order.status = CustomerOrderStatus.FILLED

    def stow_inventory(self, env, warehouse, product_type, amount, name):
        """ Stow inventory process generator for random inventory policy. 
        During lifetime will generate put() request events from stowing 
        inventory in containers. Inventory is stored in order 1->2->3->4
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            product_type (str): product type to stow
            amount (int): number of product units to stow
            name (str): name to identify associated stower
        """
        # split amount for the four bins
        split_amount, split_remain = divmod(amount,4)
        # simulate travel time from inbound parking to storage then continue
        yield env.timeout(120)
        # track total time to stow items
        total_stow_time = 120
        # move to each bin in order and store a portion of the product units
        for bin_loc in range(1,5):
            bin_amount = split_amount
            move_time = 60
            # set bin parameters
            if bin_loc == 1:
                inventory_bin = self.bin1
                # initial bin, no move "between" cost
                move_time = 0
            elif bin_loc == 2: inventory_bin = self.bin2
            elif bin_loc == 3: inventory_bin = self.bin3 
            elif bin_loc == 4: 
                inventory_bin = self.bin4
                # fourth bin, include the remained from uneven division
                bin_amount = bin_amount + split_remain
            # simulate time to move between bin locations
            yield env.timeout(move_time)
            # update total time to stow items
            total_stow_time = total_stow_time + move_time
            # until all units have been stowed, stow the next unit of product
            while bin_amount > 0:
                # wait time to stow individual unit
                yield env.timeout(10)
                # update total time to stow items
                total_stow_time = total_stow_time + 10
                # put() request adds a one unit to associated product container
                inventory_bin.get_product_container(product_type).put(1)
                bin_amount = bin_amount - 1
        # simulate travel time back to inbound parking
        yield env.timeout(120) 
        # update total time to stow items
        total_stow_time = total_stow_time + 120

"""
FulfillmentCenter objects connect the different components of a simulation by
tracking shared variables and offering helper functions.
"""
class FulfillmentCenter:
    def __init__(self, env, storage_type, inbound_delivery_daily, shift_schedule, num_packing_stations, logging=True):
        """ __init___

        Args:
            env (simpy.Environment): simulation environment
            storage_type (str): either 'designated' or 'random'
        """
        self.env = env
        self.logging = logging

        #-----------------------------------------------------------------------
        # conceptual model givens
        #-----------------------------------------------------------------------
        self.initial_qtys = {
            'tshirt': 10000,
            'hoodie': 5000,
            'spants': 5000,
            'sneaks': 3333}
        self.unit_gross_profit = {
            'tshirt':4,
            'hoodie':10,
            'spants':10,
            'sneaks':20}
        self.unit_lost_sales_penalty = {
            'tshirt':1,
            'hoodie':6,
            'spants':6,
            'sneaks':10}
        self.unit_holding_rate_per_day = {
            'tshirt':.1,
            'hoodie':.3,
            'spants':.3,
            'sneaks':.6}
        self.unit_holding_rate_per_timestep = {
            'tshirt':self.unit_holding_rate_per_day['tshirt']/86400,
            'hoodie':self.unit_holding_rate_per_day['hoodie']/86400,
            'spants':self.unit_holding_rate_per_day['spants']/86400,
            'sneaks':self.unit_holding_rate_per_day['sneaks']/86400}
        self.unit_weight = {
            'tshirt':.5,
            'hoodie':1,
            'spants':1,
            'sneaks':1.5}     
        self.delivery_fee = {
            'daily':10000,
            'weekly':50000}
        self.hourly_wage = 22.5
        
        #-----------------------------------------------------------------------
        # set decision policies based from params
        #-----------------------------------------------------------------------

        # intialize inventory storage with designated or random policy
        if storage_type == 'designated':
            self.inventory = DesignatedInventoryStorage(env, self.initial_qtys)
        elif storage_type == 'random':
            self.inventory = RandomInventoryStorage(env, self.initial_qtys)

        # initialize static delivery schedule over 52 weeks
        self.inbound_delivery_daily = inbound_delivery_daily
        # DateTime week number is based on full calendar year, week_offset used
        # to set simulation first week as week 1 and increment from there
        self.week_offset = self.get_datetime().isocalendar()[1]-1
        # use daily delivery schedule to calculate a weekly schedule
        self.inbound_delivery_weekly = {}
        for i in range(1, 53):
            self.inbound_delivery_weekly[i] = {'tshirt':0,'hoodie':0,'spants':0,'sneaks':0}
            for day in self.inbound_delivery_daily[i]:
                self.inbound_delivery_weekly[i]['tshirt'] = (
                    self.inbound_delivery_weekly[i]['tshirt'] +
                    self.inbound_delivery_daily[i][day]['tshirt']) 
                self.inbound_delivery_weekly[i]['hoodie'] = (
                    self.inbound_delivery_weekly[i]['hoodie'] +
                    self.inbound_delivery_daily[i][day]['hoodie'])
                self.inbound_delivery_weekly[i]['spants'] = (
                    self.inbound_delivery_weekly[i]['spants'] +
                    self.inbound_delivery_daily[i][day]['spants'])
                self.inbound_delivery_weekly[i]['sneaks'] = (
                    self.inbound_delivery_weekly[i]['sneaks'] +
                    self.inbound_delivery_daily[i][day]['sneaks'])          
        # delivery frequency will be set by inbound_recieving_dock process
        self.delivery_frequency = 'None'
        # inbound deliveries will land in inbound_parking, intially empty
        self.inbound_parking = InventoryBin(env, 1, {
            'tshirt':0,
            'hoodie':0,
            'spants':0,
            'sneaks':0})
        # inbound parking max capacity (in lbs)
        self.inbound_parking_capacity = 50000

        # set shift schedule for workers (pickers, packers, and stowers) 
        self.shift_schedule = shift_schedule
        # 8 hour shifts
        self.shift_length = 8*60*60
        # set initial shift to 'evening' as the simulation will begin with a
        # shift change from evening to morning
        self.current_shift = 'evening'

        # set number of packing stations and install them
        self.num_packing_stations = num_packing_stations
        self.packing_stations = {}
        for i in range(1, self.num_packing_stations+1):
            self.packing_stations[i] = PackingStation(env, i)

        # create Store object to handle recieved orders
        self.order_store = simpy.Store(env)

        #-----------------------------------------------------------------------
        # KPI Tracking
        #-----------------------------------------------------------------------

        # define log schemas
        self.log_end_of_shift_kpis = pd.DataFrame(columns=[
            'idx',
            'weekday',
            'shift',
            'current_level_parking_tshirt',
            'current_level_parking_hoodie',
            'current_level_parking_spants',
            'current_level_parking_sneaks',
            'current_level_storage_tshirt',
            'current_level_storage_hoodie',
            'current_level_storage_spants',
            'current_level_storage_sneaks',
            'current_packing_stations_queue',
            'total_orders_shipped',
            'total_orders_cancelled',
            'total_orders_discarded',
            'total_gross_proft',
            'total_delivery_expense',
            'total_delivery_expense_returns',
            'total_labor_expense',
            'total_labor_expense_overtime',
            'total_inventory_holding_cost',
            'total_lost_sales_penalty',
            'fixed_cost_facilities',
            'fixed_cost_packing_stations'])
        self.log_processed_orders = pd.DataFrame(columns=[
            'idx',
            'status',
            'time_to_process',
            'arrival_time',
            'time_to_arrive',
            'qty_tshirt',
            'qty_hoodie',
            'qty_spants',
            'qty_sneaks',
            'allocated_tshirt',
            'allocated_hoodie', 
            'allocated_spants',
            'allocated_sneaks'])
        self.log_picker = pd.DataFrame(columns=[
            'shift_start',
            'date',
            'weekday',
            'shift',
            'name',
            'idle_time',
            'active_time',
            'discarded_time',
            'num_orders_fulfilled',
            'num_orders_discarded',
            'overtime',
            'utilization'])
        self.log_packer = pd.DataFrame(columns=[
            'shift_start',
            'date',
            'weekday',
            'shift',
            'name',
            'idle_time',
            'active_time',
            'num_orders_shipped',
            'stationed_at',
            'overtime',
            'utilization'])
        self.log_stower = pd.DataFrame(columns=[
            'shift_start',
            'date',
            'weekday',
            'shift',
            'name',
            'idle_time',
            'active_time',
            'num_trips',
            'total_weight_stowed',
            'overtime',
            'utilization'])
        # initialize variables for storing kpi metrics
        self.orders_shipped = 0
        self.orders_cancelled = 0
        self.orders_discarded = 0
        self.gross_profit = 0
        self.delivery_expense = 0
        self.delivery_expense_returns = 0
        self.labor_expense = 0
        self.labor_expense_overtime = 0
        self.lost_sales_penalty = 0
        # fixed costs do not change throughout the simulation
        self.fixed_cost_facilities = 5000000
        self.fixed_cost_packing_stations = self.num_packing_stations*50000
        
        # track total items of each type from inventory parking to shipped for
        # calculating holding cost
        self.inventory_tracker = InventoryBin(env, 1, {
            'tshirt':self.initial_qtys['tshirt'],
            'hoodie':self.initial_qtys['hoodie'],
            'spants':self.initial_qtys['spants'],
            'sneaks':self.initial_qtys['sneaks']})
        self.inventory_holding_cost = 0

    def remove_from_inventory_tracker(self, env, order):
        """ Removes inventory equal to items allocated to a customer order from
        the inventory_tracker (which is used for calculating holding cost). 
        
        Args:
            env (simpy.Environment): simulation environment
            order (CustomerOrder): order to 
        """
        if order.allocated_tshirt > 0:
            self.inventory_tracker.get_product_container('tshirt').get(order.allocated_tshirt)
        if order.allocated_hoodie > 0:
            self.inventory_tracker.get_product_container('hoodie').get(order.allocated_hoodie)
        if order.allocated_spants > 0:
            self.inventory_tracker.get_product_container('spants').get(order.allocated_spants)
        if order.allocated_sneaks > 0:
            self.inventory_tracker.get_product_container('sneaks').get(order.allocated_sneaks)

    def get_optimal_packing_station_queue(self):
        """ Return packing station with the least amount of orders waiting to be
        completed. If multiple packing stations have the same amount of orders 
        waiting to be completed, then select on randomly.

        Returns:
            simpy.resource.Store: selected packing station
        """
        # get packing station queue lengths for all packing stations
        queue_lengths = []
        for i in self.packing_stations:
            queue_lengths.append(len(self.packing_stations[i].queue.items))
        # find min packing station queue length
        min_length = min(queue_lengths)

        # get list of packing stations with least amount of orders
        min_queues = []
        for i in self.packing_stations:
            if len(self.packing_stations[i].queue.items) == min_length:
                min_queues.append(i)
        # randomly select from packing stations with least amount of orders
        packing_station_id = random.choice(min_queues)

        # return packing station store
        return self.packing_stations[packing_station_id].queue

    def get_total_packing_queue(self):
        """ Helper function to get the number of items in all packing queues.

        Return:
            int: total summed count of items in all packing queues
        """
        total_queue = 0
        for i in self.packing_stations:
            total_queue += len(self.packing_stations[i].queue.items)
        return total_queue

    def get_datetime(self, seconds_offset=0):
        """ Helper function converts simulation time to human readable datetime.
        Assumes simulation starts on Thursday, October 22, 2020 @ 12:00 AM.

        Return:
            native datetime object: utc representation of time
        """
        start_date = datetime.datetime(2020, 10, 22, 0, 0, tzinfo=None) 
        # datetime epoch starts on January 1, 1970 @ 12:00 AM
        # subtract package start date from our start date and get seconds
        start_date_in_seconds = (
            start_date-datetime.datetime(1970,1,1,0,0,tzinfo=None)
            ).total_seconds()
        # return converted datetime
        return datetime.datetime.fromtimestamp(
            start_date_in_seconds + (self.env.now-seconds_offset)
            ).astimezone(datetime.timezone.utc)

    def get_week_num(self):
        """ Calculate the current week number by subtracting an offset 
        representing the number of weeks from the beginning of the calendar 
        year to the first week of the simulation.

        Return:
            int: the current week number
        """
        # monday is first day in the calendar, subtract local offset to change
        local_offset = 86400*3
        return self.get_datetime(local_offset).isocalendar()[1] - warehouse.week_offset

    def log_kpis(self, env, weekday):
        """ Writes basic kpis to disk.

        Args:
            env (simpy.Environment): simulation environment
            weekday (str): day of the week
        """
        self.log_end_of_shift_kpis = self.log_end_of_shift_kpis.append({
            'idx':env.now,
            'weekday':weekday,
            'shift':self.current_shift,
            'current_level_parking_tshirt':self.inbound_parking.avail_tshirt.level,
            'current_level_parking_hoodie':self.inbound_parking.avail_hoodie.level,
            'current_level_parking_spants':self.inbound_parking.avail_spants.level,
            'current_level_parking_sneaks':self.inbound_parking.avail_sneaks.level,
            'current_level_storage_tshirt':self.inventory.bin1.avail_tshirt.level + self.inventory.bin2.avail_tshirt.level + self.inventory.bin3.avail_tshirt.level + self.inventory.bin4.avail_tshirt.level,
            'current_level_storage_hoodie':self.inventory.bin1.avail_hoodie.level + self.inventory.bin2.avail_hoodie.level + self.inventory.bin3.avail_hoodie.level + self.inventory.bin4.avail_hoodie.level,
            'current_level_storage_spants':self.inventory.bin1.avail_spants.level + self.inventory.bin2.avail_spants.level + self.inventory.bin3.avail_spants.level + self.inventory.bin4.avail_spants.level,
            'current_level_storage_sneaks':self.inventory.bin1.avail_sneaks.level + self.inventory.bin2.avail_sneaks.level + self.inventory.bin3.avail_sneaks.level + self.inventory.bin4.avail_sneaks.level,
            'current_packing_stations_queue':self.get_total_packing_queue(),
            'total_orders_shipped':self.orders_shipped,
            'total_orders_cancelled':self.orders_cancelled,
            'total_orders_discarded':self.orders_discarded,
            'total_gross_proft':self.gross_profit,
            'total_delivery_expense':self.delivery_expense,
            'total_delivery_expense_returns':self.delivery_expense_returns,
            'total_labor_expense':self.labor_expense,
            'total_labor_expense_overtime':self.labor_expense_overtime,
            'total_inventory_holding_cost':self.inventory_holding_cost,
            'total_lost_sales_penalty':self.lost_sales_penalty,
            'fixed_cost_facilities':self.fixed_cost_facilities,
            'fixed_cost_packing_stations':self.fixed_cost_packing_stations}, ignore_index=True)

    def write_sim_logs(self, env, sim_run_name):
        """ Write simulation logs for kpis, orders, and workers to disk.

        Args:
            env (simpy.Environment): simulation environment
            sim_run_name (str): unique simulation name to add as prefix
        """
        # set folder path based on the name of a simulation run
        folder_path = f'logs\\{sim_run_name}'
        # if the folder doesn't exist, make it
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        self.log_end_of_shift_kpis.to_csv(f'{folder_path}\\{sim_run_name}_log_EOS_kpis.csv', index=False)
        self.log_processed_orders.to_csv(f'{folder_path}\\{sim_run_name}_log_processed_orders.csv', index=False)
        self.log_picker.to_csv(f'{folder_path}\\{sim_run_name}_log_picker.csv', index=False)
        self.log_packer.to_csv(f'{folder_path}\\{sim_run_name}_log_packer.csv', index=False)
        self.log_stower.to_csv(f'{folder_path}\\{sim_run_name}_log_stower.csv', index=False)

    def write_final_results_log(self, env, sim_run_name):
        """ Calculate total profit and write final log to disk.

        Args:
            env (simpy.Environment): simulation environment
            sim_run_name (str): unique simulation name to add as prefix
        """
        # set folder path based on the name of a simulation run
        folder_path = f'logs\\{sim_run_name}'
        # if the folder doesn't exist, make it
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # calculate total profit
        total_profit = (
            warehouse.gross_profit -
            (
                self.delivery_expense +
                self.delivery_expense_returns +
                self.labor_expense +
                self.labor_expense_overtime +
                self.inventory_holding_cost +
                self.lost_sales_penalty +
                self.fixed_cost_packing_stations
            ))
        # write run's final results to disk
        with open(f'{folder_path}\\profit_{total_profit}.txt', 'w') as f:
                print(f'total_gross_profit: {self.gross_profit}', file=f)
                print(f'total_delivery_expense: {self.delivery_expense}', file=f)
                print(f'total_delivery_expense_returns: {self.delivery_expense_returns}', file=f)
                print(f'total_labor_expense: {self.labor_expense}', file=f)
                print(f'total_labor_expense_overtime: {self.labor_expense_overtime}', file=f)
                print(f'total_inventory_holding_cost: {self.inventory_holding_cost}', file=f)
                print(f'total_lost_sales_penalty: {self.lost_sales_penalty}', file=f)
                print(f'fixed_cost_packing_stations: {self.fixed_cost_packing_stations}', file=f)
                print(f'fixed_cost_facilities: {self.fixed_cost_facilities}', file=f)
                print(f'===============================================', file=f)
                print(f'total profit w/o facilities cost: {total_profit}', file=f)
                print(f'total profit with facilities cost: {total_profit - warehouse.fixed_cost_facilities}', file=f)
    
################################################################################
## Process Generator Functions
################################################################################

def write_logs(env, warehouse, sim_run_name, save_rate):
    """ Process generator for regulating debug log writing to disk.
    
    Args:
            env (simpy.Environment): simulation environment
            warehouse (FulfillmentCenter): manages state of the facility
            sim_run_name (str): unique simulation name to add as prefix
    """
    while(True):
        # write logs at specified save rate
        yield env.timeout(save_rate)
        # save logs to file (replacing previous logs)
        warehouse.write_sim_logs(env, sim_run_name)

def print_kpis(env, warehouse, print_rate):
    """ Process generator for printing kpis to the terminal. Debug function for 
    displaying kpis at a specified rate while running the simulation.

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        print_rate (int): number of seconds to wait between printing kpis
    """
    while True:
        print(f'{env.now}:\t============== KPIS ==============')
        print(f'\torders shipped: {warehouse.orders_shipped}')
        print(f'\torders cancelled: {warehouse.orders_cancelled}')
        print(f'\torders discarded: {warehouse.orders_discarded}')
        print(f'\tgross proft: {warehouse.gross_profit}')
        print(f'\tdelivery expense: {warehouse.delivery_expense}')
        print(f'\tdelivery expense returns: {warehouse.delivery_expense_returns}')
        print(f'\tlabor expense: {warehouse.labor_expense}')
        print(f'\tlabor expense overtime: {warehouse.labor_expense_overtime}')
        print(f'\tlost sales penalty: {warehouse.lost_sales_penalty}')
        print(f'\tinventory holding cost: {warehouse.inventory_holding_cost}')
        print(f'\t==================================')

        yield env.timeout(print_rate)

def holding_cost_monitor(env, warehouse):
    """ Process generator for realizing inventory holding costs. Calculates 
    holding costs for ever "simulation second."

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
    """
    while True:
        # calculate holding cost for a single time step
        tshirt_holding_cost = warehouse.inventory_tracker.avail_tshirt.level*(
            warehouse.unit_holding_rate_per_timestep['tshirt'])
        hoodie_holding_cost = warehouse.inventory_tracker.avail_hoodie.level*(
            warehouse.unit_holding_rate_per_timestep['hoodie'])
        spants_holding_cost = warehouse.inventory_tracker.avail_spants.level*(
            warehouse.unit_holding_rate_per_timestep['spants'])
        sneaks_holding_cost = warehouse.inventory_tracker.avail_sneaks.level*(
            warehouse.unit_holding_rate_per_timestep['sneaks'])
        # incur holding cost to warehouse
        warehouse.inventory_holding_cost = (
            warehouse.inventory_holding_cost +
            tshirt_holding_cost +
            hoodie_holding_cost +
            spants_holding_cost +
            sneaks_holding_cost)
        # wait until next timestep to continue
        yield env.timeout(1)

def inbound_recieving_dock(env, warehouse, freq):
    """ Process generator for recieving inbound product deliveries. 
        During lifetime will generate get() request events from inventory 
        containers.
        
    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        freq (str): specify 'daily' or 'weekly' shipment delivery frequency
    """
    week_num = warehouse.get_week_num()

    # setup recieving dock for daily or weekly deliveries
    if freq == 'daily':
        # calulate first inbound recieving time (today, 9:00 AM)
        initial_wait = 9*60*60
        wait = 24*60*60
    elif freq == 'weekly':
        # calulate first inbound recieving time (Monday, 9:00 AM)
        initial_wait = (9*60*60)+(86400*4)
        wait = 7*24*60*60
    
    # set delivery frequency for the warehouse
    warehouse.delivery_frequency = freq

    # simulate wait until first shipment is delivered
    yield env.timeout(initial_wait)

    # continuously run recieving dock process until simulation ends
    while True:
        week_num = warehouse.get_week_num()

        # incur delivery fee
        warehouse.delivery_expense += warehouse.delivery_fee[freq]
        if freq == 'daily':
            weekday = warehouse.get_datetime().strftime("%A")
            shipment_schedule = warehouse.inbound_delivery_daily[week_num][weekday]
        elif freq == 'weekly':
            shipment_schedule = warehouse.inbound_delivery_weekly[week_num]

        # calculate remaining capacity
        remaining_capacity = warehouse.inbound_parking_capacity - (
            warehouse.inbound_parking.avail_tshirt.level*warehouse.unit_weight['tshirt'] +
            warehouse.inbound_parking.avail_hoodie.level*warehouse.unit_weight['hoodie'] +
            warehouse.inbound_parking.avail_spants.level*warehouse.unit_weight['spants'] +
            warehouse.inbound_parking.avail_sneaks.level*warehouse.unit_weight['sneaks']
        )
        # get shipment quantities
        inbound_tshirt = shipment_schedule['tshirt']
        inbound_hoodie = shipment_schedule['hoodie']
        inbound_spants = shipment_schedule['spants']
        inbound_sneaks = shipment_schedule['sneaks']
        # calculate total shipment weight
        shipment_weight = (
            inbound_tshirt*warehouse.unit_weight['tshirt'] +
            inbound_hoodie*warehouse.unit_weight['hoodie'] +
            inbound_spants*warehouse.unit_weight['spants'] +
            inbound_sneaks*warehouse.unit_weight['sneaks']
        )
        if shipment_weight > remaining_capacity:
            # incur fee for returning items that cannot be recieved
            warehouse.delivery_expense_returns += warehouse.delivery_fee[freq]
            # update inbound values
            product_allowed_weight = divmod(shipment_weight,4)[0]
            inbound_tshirt = min(inbound_tshirt, divmod(product_allowed_weight, warehouse.unit_weight['tshirt'])[0])
            inbound_hoodie = min(inbound_hoodie, divmod(product_allowed_weight, warehouse.unit_weight['hoodie'])[0])
            inbound_spants = min(inbound_spants, divmod(product_allowed_weight, warehouse.unit_weight['spants'])[0])
            inbound_sneaks = min(inbound_sneaks, divmod(product_allowed_weight, warehouse.unit_weight['sneaks'])[0])

        # recieve inbound shipment
        if inbound_tshirt > 0:
            # put tshirts in parking
            yield warehouse.inbound_parking.avail_tshirt.put(inbound_tshirt)
            # track tshirts for holding cost caluclation
            yield warehouse.inventory_tracker.avail_tshirt.put(inbound_tshirt)
        if inbound_hoodie > 0:
            # put hoodies in parking
            yield warehouse.inbound_parking.avail_hoodie.put(inbound_hoodie)
            # track hoodies for holding cost caluclation
            yield warehouse.inventory_tracker.avail_hoodie.put(inbound_hoodie)
        if inbound_spants > 0:
            # put spants in parking
            yield warehouse.inbound_parking.avail_spants.put(inbound_spants)
            # track spants for holding cost caluclation
            yield warehouse.inventory_tracker.avail_spants.put(inbound_spants)
        if inbound_sneaks > 0:
            # put sneaks in parking
            yield warehouse.inbound_parking.avail_sneaks.put(inbound_sneaks)
            # track sneaks for holding cost caluclation
            yield warehouse.inventory_tracker.avail_sneaks.put(inbound_sneaks)

        # simulate wait time for next shipment
        yield env.timeout(wait)
        
def order_reciever(env, warehouse, orders_source): 
    """ Process generator for recieving customer orders 
        During lifetime will process each order as it arrives.
        
    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        orders_source (list): list of CustomerOrder objects with arrival times
    """
    # process each order from the order source FIFO until no orders are left
    while len(orders_source) > 0:
        # pop first order from orders source
        new_order = orders_source.pop(0)
        # calulate when order will arrive relative to now
        wait = max(0, new_order.arrival_time - env.now)
        # simulate wait for order to arrive
        yield env.timeout(wait)
        # order has arrived, update order status
        new_order.status = CustomerOrderStatus.ARRIVED
        new_order.time_to_arrive = env.now
        # kick off process to monitor age of order and cancel when expired
        env.process(order_age_monitor(env, warehouse, new_order))
        # create a new put() request event to add order to warehouse store
        warehouse.order_store.put(new_order)

def order_age_monitor(env, warehouse, order):
    """ Process generator for monitoring a single order. Cancels order if it
    expires (i.e. customer cancels after 72 hours).

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        order (CustomerOrder): order to monitor
    """
    # simulate lifetime of the order
    yield env.timeout(order.ORDER_EXPIRATION)
    # cancel order if it has not been shipped
    if order.status != CustomerOrderStatus.SHIPPED:
        order.status = CustomerOrderStatus.CANCELLED
        # update debug log
        if warehouse.logging:
            order.log_processed_order(env, warehouse)
        # increment number of orders cancelled
        warehouse.orders_cancelled += 1
        # incur sales penalty
        warehouse.lost_sales_penalty += order.get_lost_sales_penalty(env, warehouse)
        # stop tracking inventory for holding cost
        warehouse.remove_from_inventory_tracker(env, order)

def shift_manager(env, warehouse):
    """ Process generator for managing all shifts. During lifetime (length
    of simulation) will continuously generate timeout() events to trigger shift
    changes. When a shift change occurs, shift_manager sends workers to work.

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
    """
    shift_idx = 0
    while True:
        shift_idx += 1

        starting_inventory_holding_cost = warehouse.inventory_holding_cost

        # get day of the week
        weekday = warehouse.get_datetime().strftime("%A")
        # get week number of simulation
        week_num = warehouse.get_week_num()

        # change shift in the context of the warehouse
        last_shift = warehouse.current_shift
        if last_shift == 'morning': 
            warehouse.current_shift = 'afternoon'
        elif last_shift == 'afternoon': 
            warehouse.current_shift = 'evening'
        elif last_shift == 'evening': 
            warehouse.current_shift = 'morning'
        print(f'-----\tshift change: {last_shift} to {weekday} {warehouse.current_shift}, week_num: {warehouse.get_week_num()}\t@ {warehouse.get_datetime()} -----')
        # send pickers to work
        for i in range(1, warehouse.shift_schedule[week_num][weekday][warehouse.current_shift]['num_pickers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new picker
            env.process(worker_shift(env, warehouse, name, 'picker'))
        # send stowers to work
        for i in range(1, warehouse.shift_schedule[week_num][weekday][warehouse.current_shift]['num_stowers']+1):
           name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new stower
           env.process(worker_shift(env, warehouse, name, 'stower'))
        # send packers to work
        for i in range(1, warehouse.shift_schedule[week_num][weekday][warehouse.current_shift]['num_packers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new packer
            env.process(worker_shift(env, warehouse, name, 'packer'))

          # simulate wait time until next shift change
        yield env.timeout(warehouse.shift_length)

        shift_inventory_holding_cost = warehouse.inventory_holding_cost-starting_inventory_holding_cost
        
        # update debug log
        if warehouse.logging:
            warehouse.log_kpis(env, weekday)

def worker_shift(env, warehouse, name, worker_type):
    """ Process generator for managing individual shift of a worker. During 
    lifetime generates processes specific to the specified worker type. Manages
    length of the shift and sends workers home when their shift is over. If the
    work is still working at the end of the shift, they will finish their task
    and book overtime before heading home. 

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        name (str): arbitrary value used to identify the worker
        worker_type (str): 'picker', 'packer', or 'stower'
    """
    # calculate end of worker's shift
    end_shift_time = env.now + warehouse.shift_length

    # start shift, worker is now working
    working = True
    # packer station assignment intially 0 aka "no assignment"
    stationed_at = 0
    stations = warehouse.packing_stations

    # intialize debug log dictionaries
    if warehouse.logging:
        #setup log for worker
        if worker_type == 'picker':
            log = {'shift_start':env.now,
                'date':warehouse.get_datetime().strftime('%m/%d/%Y'),
                'weekday':warehouse.get_datetime().strftime('%A'),
                'shift':warehouse.current_shift,
                'name':name,
                'idle_time':0,
                'active_time':0,
                'discarded_time':0,
                'num_orders_fulfilled':0,
                'num_orders_discarded':0,
                'overtime':0,
                'utilization':0}
        elif worker_type == 'packer':
            log = {'shift_start':env.now,
                'date':warehouse.get_datetime().strftime('%m/%d/%Y'),
                'weekday':warehouse.get_datetime().strftime('%A'),
                'shift':warehouse.current_shift,
                'name':name,
                'idle_time':0,
                'active_time':0,
                'num_orders_shipped':0,
                'stationed_at':0,
                'overtime':0,
                'utilization':0}
        elif worker_type == 'stower':
            log = {'shift_start':env.now,
                'date':warehouse.get_datetime().strftime('%m/%d/%Y'),
                'weekday':warehouse.get_datetime().strftime('%A'),
                'shift':warehouse.current_shift,
                'name':name,
                'idle_time':0,
                'active_time':0,
                'num_trips':0,
                'total_weight_stowed':0,
                'overtime':0,
                'utilization':0}
    #===========================================================================
    
    # while worker is still working, continue working
    while working:
        # calculate remaining time in worker's shift
        remaining_time_in_shift = max(0, end_shift_time - env.now)
        # if worker's shift is over, send worker home, otherwise perform task
        if env.now >= end_shift_time:
            working = False
            # calculate overtime
            overtime = env.now - end_shift_time
            # update debug log
            if warehouse.logging:
                log['overtime'] = overtime
                log['utilization'] = (
                    (log['active_time'] + log['overtime'])/
                    (log['active_time'] + log['overtime'] + log['idle_time']))

            warehouse.labor_expense += (warehouse.hourly_wage*warehouse.shift_length/60/60)
            warehouse.labor_expense_overtime += (overtime*(warehouse.hourly_wage/60/60))

            # free up packing station when packer leaves it
            if worker_type == 'packer':
                if stationed_at != 0:
                    # bit of hack to, release slot by replacing resource
                    stations[stationed_at].slots = simpy.Resource(
                        env, capacity=1)
                # update debug log (packer only)
                if warehouse.logging:
                    warehouse.log_packer = warehouse.log_packer.append(
                        log, ignore_index=True)
            # update debug log (picker and stower)
            if warehouse.logging:
                if worker_type == 'picker':
                    warehouse.log_picker = warehouse.log_picker.append(
                        log, ignore_index=True)
                if worker_type == 'stower':
                    warehouse.log_stower = warehouse.log_stower.append(
                        log, ignore_index=True)
        else:
            if worker_type == 'stower':
                # generate stower process
                log_details = yield env.process(stower(env, warehouse, name))
                # update debug log
                if warehouse.logging:
                    if log_details['result'] =='idle':
                        log['idle_time'] += log_details['process_time']
                    elif log_details['result'] == 'stowed':
                        log['num_trips'] += 1
                        log['active_time'] += log_details['process_time']
                        log['total_weight_stowed'] += log_details['weight_stowed']
            elif worker_type == 'picker':
                # generate picker process
                log_details = yield env.process(picker(env, warehouse, name))
                # update debug log
                if warehouse.logging:
                    if log_details['result'] =='idle':
                        log['idle_time'] += log_details['process_time']
                    elif log_details['result']=='fulfilled':
                        log['num_orders_fulfilled'] += 1
                        log['active_time'] += log_details['process_time']
                    elif log_details['result'] =='discarded':
                        log['num_orders_discarded'] += 1
                        log['discarded_time'] += log_details['process_time']
            elif worker_type == 'packer':
                # if not stationed at a packing station, check if one is open
                if stationed_at == 0:
                    for i in stations:
                        # check if any other packers are stationed at station i
                        if stations[i].slots.count == 0:
                            # request() event to station packer at station i
                            slot_request = stations[i].slots.request()
                            if slot_request.triggered:
                                # packing station i is free
                                stationed_at = i
                                # update debug log
                                if warehouse.logging:
                                    log['stationed_at'] = stationed_at
                                break
                if stationed_at == 0:
                    # packer not stationed at a packing station, remain idle
                    yield env.timeout(1)
                    # update debug log
                    if warehouse.logging:
                        log['idle_time'] += 1
                else:
                    # generate packer process
                    log_details = yield env.process(packer(
                        env, warehouse, stationed_at, name))
                    # update debug log
                    if warehouse.logging:
                        if log_details['result'] =='idle':
                            log['idle_time'] += log_details['process_time']
                        elif log_details['result'] == 'shipped':
                            log['num_orders_shipped'] += 1
                            log['active_time'] += log_details['process_time']

def picker(env, warehouse, name):
    """ Process generator for picker activity. The picker checks for
    unfulfilled orders, if any are available the picker engages in the picking
    operation. The picker is assigned a single order to pick (in FIFO order),
    picks up the appropriate inventory, and sends the order to a packing 
    station.

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        name (str): arbitrary value used to identify the picker
    """
    log_picker_start = env.now
    log_result = 'idle'

    # if order is available, work on it
    if len(warehouse.order_store.items) > 0:
        # attempt to get an order from the order_store (should always work)
        order = yield warehouse.order_store.get()
         # if order has not been cancelled, run picker item pickup service
        if order.status != CustomerOrderStatus.CANCELLED:
            # check if order can be fulfilled with current inventory, if not, discard order, otherwise pick up for order
            if warehouse.inventory.check_inventory(env, order):
                # pickup inventory for order
                yield env.process(warehouse.inventory.pickup_inventory(env, warehouse, order, name))
                # wait time to send picked products from the picking station to the packing station before starting another trip
                yield env.timeout(30)
                if order.status != CustomerOrderStatus.CANCELLED:
                    order.status = CustomerOrderStatus.WAITING_TO_PACK
                    warehouse.get_optimal_packing_station_queue().put(order)
                    log_result = 'fulfilled'
            else:
                # discard order due to lack of available inventory
                order.status = CustomerOrderStatus.DISCARDED
                # update debug log
                if warehouse.logging:
                    order.log_processed_order(env, warehouse)
                # increment number of discarded orders
                warehouse.orders_discarded += 1
                # incur sales penalty
                warehouse.lost_sales_penalty += order.get_lost_sales_penalty(env, warehouse)
                # stop tracking inventory for holding cost
                warehouse.remove_from_inventory_tracker(env, order)
                log_result = 'discarded'
    else:
        # no order is available to process, wait until next timestep to check order_store again
        yield env.timeout(1)

    return {'process_time':env.now-log_picker_start, 'result':log_result}

def stower(env, warehouse, name):
    """ Process generator for the stower activity. The stower checks if inbound
    parking has any work for stowing, if any is available the stower stows work
    of the product type that has the most work remaining. 

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        name (str): arbitrary value used to identify the stower
    """
    log_stower_start = env.now
    log_result = 'idle'
    log_weight = 0

    # get product with max remaining work
    max_work_product = warehouse.inbound_parking.get_max_work_product_type(env, warehouse)
    product_type = max_work_product['product_type']
    if product_type != 'None':
        product_container = warehouse.inbound_parking.get_product_container(product_type)
        max_amount = math.floor(12/warehouse.unit_weight[product_type])
        amount = min(max_amount, product_container.level)
        # remove product from the container
        yield product_container.get(amount)
        # time to pick up from inbound parking
        yield env.timeout(120) 
        # kick of stow operation process generator
        yield env.process(warehouse.inventory.stow_inventory(env, warehouse, product_type, amount, name))
        log_result = 'stowed'
        log_weight = amount * warehouse.unit_weight[product_type]
    else:
        # no inbound work remaining to process, check again next step
        yield env.timeout(1)

    return {'process_time':env.now-log_stower_start, 'result':log_result, 'weight_stowed':log_weight}

def packer(env, warehouse, assigned_station, name):
    """ Process generator for packer activity. The packer checks for unpacked
    orders in their assigned packing station queue, if any are available the
    packer engages in the pack operation. Once packed, the order is sent
    for outbound shipping (instantanious).

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FulfillmentCenter): manages state of the facility
        assigned_station (int): index of packing station assigned to
        name (str): arbitrary value used to identify the packer
    """
    log_packer_start = env.now
    log_result = 'idle'
    
    order_queue = warehouse.packing_stations[assigned_station].queue
    if len(order_queue.items) > 0:
        order = yield order_queue.get()
        if order.status == CustomerOrderStatus.WAITING_TO_PACK:
            pack_time = (
                30 + # base time to pack
                order.allocated_tshirt*10 + # time to pack units
                order.allocated_hoodie*10 + # time to pack units
                order.allocated_spants*10 + # time to pack units
                order.allocated_sneaks*10   # time to pack units
            )
            yield env.timeout(pack_time)
            order.status = CustomerOrderStatus.SHIPPED
            log_result = 'shipped'
            # logging===========================================================
            if warehouse.logging:
                order.log_processed_order(env, warehouse)
            #===================================================================
            # increment number of orders shipped
            warehouse.orders_shipped += 1
            # book profit!
            warehouse.gross_profit += order.get_gross_profit(env, warehouse)
            # stop tracking inventory for holding cost
            warehouse.remove_from_inventory_tracker(env, order)
    else:
        # no order available, check again next timestep
        yield env.timeout(1)

    return {'process_time':env.now-log_packer_start, 'result':log_result}

################################################################################
## Additional Functions
################################################################################

def generate_order_source():
    """ Generate order details for all orders to be processed through the 
    simulation and convert into new CustomerOrder objects.

    Return:
        list: full list of all CustomerOrder objects to processed
    """
    # set varying order arrival rates by weekday and hour, the factors are 
    # multiplicative with the weekday modifying the base hourly rate
    orderWeekdayFactors = {
                        0: 2.50, 
                        1: 3.33, 
                        2: 1.42, 
                        3: 2.5, 
                        4: 1.10, 
                        5: 1.00, 
                        6: 1.25}
    orderHourFactors = {0: 30.56118, 
                        1: 54.01161, 
                        2: 106.26632, 
                        3: 207.85501, 
                        4: 215.03588, 
                        5: 213.78153, 
                        6: 111.61141, 
                        7: 45.72561, 
                        # shift afternoon
                        8: 27.29694, 
                        9: 21.61996, 
                        10: 15.47543, 
                        11: 18.15357, 
                        12: 13.54276, 
                        13: 13.46299, 
                        14: 15.28291, 
                        15: 18.14266, 
                        # shift evening
                        16: 13.57966, 
                        17: 18.0377, 
                        18: 15.60327, 
                        19: 11.97936, 
                        20: 10.75827, 
                        21: 12.09711, 
                        22: 15.45324, 
                        23: 21.59623}

    # poisson parameter for each item frequency in orders
    mean_tshirt = 1.00
    mean_hoodie = 0.50
    mean_spants = 0.50
    mean_sneaks = 0.25

    # generate list of random order arrival times
    start_date = datetime.datetime(2020, 10, 22, 0, 0, tzinfo=None)
    orderGenClock = 0
    orderTimes = []
    # generate arrival times to fill up the entire simulation time
    while orderGenClock < sim_until:
        # set order time parameter based on time of previous order
        orderDateTime = start_date + datetime.timedelta(seconds=orderGenClock)
        orderTimeMean = (orderWeekdayFactors[orderDateTime.weekday()] * 
            orderHourFactors[orderDateTime.hour])
        # generate new order time based on current order time parameter
        orderGenClock = orderGenClock + np.random.exponential(orderTimeMean)
        orderTimes.append(orderGenClock)
    print(f'generated {len(orderTimes)} orders')
    # Reverse list so we pop off the first orders first
    orderTimes.reverse()

    # generate a list of candidate orders
    candidate_orders = []
    for i in range(len(orderTimes)*2):
        candidate_order = np.random.poisson([
            mean_tshirt, 
            mean_hoodie, 
            mean_spants, 
            mean_sneaks])
        # items ordered cannot be zero, filter out blanks before order time 
        # generation to preserve statistical properties
        if candidate_order.max() > 0:
            candidate_orders.append(candidate_order)

    # populate orders with entries from the candidate order list
    orders = {}
    for i in range(len(orderTimes)):
        next_order = candidate_orders.pop()
        orders[i] = {
            'OrderTimeInSec': orderTimes.pop(), 
            'QtyShirt': next_order[0], 
            'QtyHoodie': next_order[1], 
            'QtySweatpants': next_order[2], 
            'QtySneakers': next_order[3]}
    # print order list to log
    with open('orderlog.txt', 'w') as f:
        print(orders, file=f)

    # create list of CustomerOrder objects from order details
    orders_source = []
    for idx in orders:
        orders_source.append(CustomerOrder(env, warehouse, idx, orders[idx]))

    return orders_source

################################################################################
# Set Policy Decisions (and configure simulation run)
################################################################################

#-------------------------------------------------------------------------------
# DECISION 1: Daily or weekly inbound delivery schedule.
#-------------------------------------------------------------------------------
delivery_frequency = 'daily' 

#-------------------------------------------------------------------------------
# DECISION 2: Define inbound delivery schedule details. If delivery frequency is
# set to 'weekly' the daily configurations will be summed automatically. 
#------------------------------------------------------------------------------- 
inbound_delivery_daily = {}
standard_week_deliveries = {
    # daily mean order values
    'Sunday':   {'tshirt':3675,'hoodie':1828,'spants':1852,'sneaks': 918},
    'Monday':   {'tshirt':1830,'hoodie': 916,'spants': 916,'sneaks': 459},
    'Tuesday':  {'tshirt':1374,'hoodie': 685,'spants': 689,'sneaks': 345},
    'Wednesday':{'tshirt':3218,'hoodie':1607,'spants':1607,'sneaks': 792},
    'Thursday': {'tshirt':1835,'hoodie': 927,'spants': 928,'sneaks': 460},
    'Friday':   {'tshirt':4169,'hoodie':2081,'spants':2079,'sneaks':1050},
    'Saturday': {'tshirt':4577,'hoodie':2292,'spants':2299,'sneaks':1158}}
for i in range(1,53):
    if delivery_frequency == 'weekly':
        if i == 1:  
            #-----------------------------------------------------------------------
            # SUB-DECISION: Special schedule for week 1. Applies to first Wednesday
            # of simulation.
            #-----------------------------------------------------------------------
            inbound_delivery_daily[i] = {
            # Adding additional amount in first weekly order to replenish inventory 
            # after unavoidable initial stockout. Extra amounts are shown added to 
            # Monday's order quantities.
                'Sunday':   {'tshirt':3675,'hoodie':1828,'spants':1852,'sneaks': 918},
                'Monday':   {'tshirt':1830+5000,'hoodie': 916+2500,'spants': 916+2500,'sneaks': 459+1250},
                'Tuesday':  {'tshirt':1374,'hoodie': 685,'spants': 689,'sneaks': 345},
                'Wednesday':{'tshirt':3218,'hoodie':1607,'spants':1607,'sneaks': 792},
                'Thursday': {'tshirt':1835,'hoodie': 927,'spants': 928,'sneaks': 460},
                'Friday':   {'tshirt':4169,'hoodie':2081,'spants':2079,'sneaks':1050},
                'Saturday': {'tshirt':4577,'hoodie':2292,'spants':2299,'sneaks':1158}}
        else:
            inbound_delivery_daily[i] = standard_week_deliveries

    elif delivery_frequency == 'daily':
        if i == 1:
            inbound_delivery_daily[i] = {
            # Delaying start of deliveries to run down inventory to a more 
            # optimized level
                'Sunday':   {'tshirt':3675,'hoodie':1828,'spants':1852,'sneaks': 918},
                'Monday':   {'tshirt':1830,'hoodie': 916,'spants': 916,'sneaks': 459},
                'Tuesday':  {'tshirt':1374,'hoodie': 685,'spants': 689,'sneaks': 345},
                'Wednesday':{'tshirt':3218,'hoodie':1607,'spants':1607,'sneaks': 792},
                'Thursday': {'tshirt':0,'hoodie': 0,'spants': 0,'sneaks': 0},
                'Friday':   {'tshirt':0,'hoodie':0,'spants':0,'sneaks':0},
                'Saturday': {'tshirt':4577,'hoodie':2292,'spants':2299,'sneaks':1158}}
        else:
            inbound_delivery_daily[i] = standard_week_deliveries

#-------------------------------------------------------------------------------
# DECISION 3: Choose betwen a 'designated' or 'random' storage policy. 
# Designated will increase time to pickup items for orders while decreasing 
# time to stow. Random will descrease time to pickup items for orders while
# increasing time to stow.
# ------------------------------------------------------------------------------
storage_type = 'random'

# ------------------------------------------------------------------------------
# DECISION 4: Choose the number of packing stations to install. Note that each
# packing station has fixed cost of $50,000 and only one packer may work at a
# single packing station at any given time.
# ------------------------------------------------------------------------------
num_packing_stations = 2

#-------------------------------------------------------------------------------
# DECISION 5: Set the schedules for all workers - stowers, pickers, and packers.
# Delivery frequency must be considered for stower shift assignments.
#-------------------------------------------------------------------------------
shift_schedule = {}
if delivery_frequency == 'daily':
    standard_week_schedule = {
        'Sunday': {
            'morning':   {'num_pickers':  8, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 13, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 14, 'num_stowers':  14, 'num_packers': 2}},
        'Monday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 1},
            'afternoon': {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 1},
            'evening':   {'num_pickers':  7, 'num_stowers':   7, 'num_packers': 1}},
        'Tuesday': {
            'morning':   {'num_pickers':  3, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers':  5, 'num_stowers':   5, 'num_packers': 2}},
        'Wednesday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 11, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 12, 'num_stowers':  12, 'num_packers': 2}},
        'Thursday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers':  6, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers':  7, 'num_stowers':   7, 'num_packers': 2}},
        'Friday': {
            'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 16, 'num_stowers':  16, 'num_packers': 2}},
        'Saturday': {
            'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 1},
            'afternoon': {'num_pickers': 15, 'num_stowers':   0, 'num_packers': 1},
            'evening':   {'num_pickers': 17, 'num_stowers':  18, 'num_packers': 1}}}

    for i in range(1,53):
        if i == 1: # DECISION: Special schedule for week 1 (Applies to first Wednesday of simulation)
            shift_schedule[i] = {
                'Sunday': {
                    'morning':   {'num_pickers':  8, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 13, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 14, 'num_stowers':  14, 'num_packers': 2}},
                'Monday': {
                    'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 1},
                    'afternoon': {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 1},
                    'evening':   {'num_pickers':  7, 'num_stowers':   7, 'num_packers': 1}},
                'Tuesday': {
                    'morning':   {'num_pickers':  3, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers':  5, 'num_stowers':   5, 'num_packers': 2}},
                'Wednesday': {
                    'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 11, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 12, 'num_stowers':  12, 'num_packers': 2}},
                'Thursday': {
                    'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers':  6, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2}},
                'Friday': {
                    'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 16, 'num_stowers':   0, 'num_packers': 2}},
                'Saturday': {
                    'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 1},
                    'afternoon': {'num_pickers': 15, 'num_stowers':   0, 'num_packers': 1},
                    'evening':   {'num_pickers': 17, 'num_stowers':  18, 'num_packers': 1}}}
        else:
            shift_schedule[i] = standard_week_schedule
# use a different stower schedule if only recieving delivery once per week
elif delivery_frequency == 'weekly':
    standard_week_schedule = {
        'Sunday': {
            'morning':   {'num_pickers':  8, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 13, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2}},
        'Monday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 1},
            'afternoon': {'num_pickers':  7, 'num_stowers':  42, 'num_packers': 1},
            'evening':   {'num_pickers':  7, 'num_stowers':  42, 'num_packers': 1}},
        'Tuesday': {
            'morning':   {'num_pickers':  3, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2}},
        'Wednesday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 11, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 12, 'num_stowers':   0, 'num_packers': 2}},
        'Thursday': {
            'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers':  6, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2}},
        'Friday': {
            'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
            'afternoon': {'num_pickers': 15, 'num_stowers':   0, 'num_packers': 2},
            'evening':   {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 2}},
        'Saturday': {
            'morning':   {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1},
            'afternoon': {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1},
            'evening':   {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1}}}
    for i in range(1,53):
        if i == 1: # DECISION: Special schedule for week 1 (Applies to first Wednesday of simulation)
            shift_schedule[i] = {
                'Sunday': {
                    'morning':   {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 14, 'num_stowers':   0, 'num_packers': 2}},
                'Monday': {
                    'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers':  7, 'num_stowers':  54, 'num_packers': 2},
                    'evening':   {'num_pickers':  7, 'num_stowers':  54, 'num_packers': 2}},
                'Tuesday': {
                    'morning':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers':  5, 'num_stowers':   0, 'num_packers': 2}},
                'Wednesday': {
                    'morning':   {'num_pickers': 12, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 12, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 12, 'num_stowers':   0, 'num_packers': 2}},
                'Thursday': {
                    'morning':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers':  7, 'num_stowers':   0, 'num_packers': 2}},
                'Friday': {
                    'morning':   {'num_pickers': 16, 'num_stowers':   0, 'num_packers': 2},
                    'afternoon': {'num_pickers': 16, 'num_stowers':   0, 'num_packers': 2},
                    'evening':   {'num_pickers': 16, 'num_stowers':   0, 'num_packers': 2}},
                'Saturday': {
                    'morning':   {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1},
                    'afternoon': {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1},
                    'evening':   {'num_pickers': 17, 'num_stowers':   0, 'num_packers': 1}}}
        else:
            shift_schedule[i] = standard_week_schedule

#-------------------------------------------------------------------------------
# Configure Simulation Run
#-------------------------------------------------------------------------------
# set number of simulation seconds to run until, 1 day == 86400 seconds
sim_until = 86401*7*3
# set rate (in simulation seconds) to print kpis, 1 shift == 28800 seconds
sim_print_rate = 28800
# set rate (in simulation seconds) to write full log details to disk
sim_log_save_rate = 86400*1

################################################################################
## Setup and Run Simulation 
################################################################################

# set a random seed for comparing results easily
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# environment is the clock (event queue)
env = simpy.Environment()

# create warehouse with configurations, components, and kpis
warehouse = FulfillmentCenter(env, 
    storage_type, 
    inbound_delivery_daily, 
    shift_schedule,
    num_packing_stations,
    # set logging to false to save time on run, will still write final log
    logging=True) 

#-------------------------------------------------------------------------------
# Write all parameters to disk
#-------------------------------------------------------------------------------
# set custom prefix to be whatever for easier log delineation
custom_prefix = "random"
sim_run_name = (custom_prefix +
    datetime.datetime.now().strftime('%m%d%Y%H%M') +
    "_until_" + str(sim_until)+delivery_frequency)

# set folder path based on the name of a simulation run
folder_path = f'logs\\{sim_run_name}'
# if the folder doesn't exist, make it
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

if warehouse.logging:
    # print parameters list to log
    with open(f'{folder_path}\\{sim_run_name}_parameters.txt', 'w') as f:
        print(f'sim_until: {sim_until}', file=f)
        print(f'storage_type: {storage_type}', file=f)
        print(f'delivery_frequency: {delivery_frequency}', file=f)
        print(f'num_packing_stations: {num_packing_stations}', file=f)
        print(f'#=====================================================', file=f)
        print(f'inbound_delivery_daily:\n{inbound_delivery_daily}', file=f)
        print(f'#=====================================================', file=f)
        print(f'shift_schedule:\n{shift_schedule}', file=f)

# generate process to handle inbound recieving
env.process(inbound_recieving_dock(env, warehouse, delivery_frequency))
# calculate holding cost every timestep
env.process(holding_cost_monitor(env, warehouse))
# print kpis for basic live monitoring
env.process(print_kpis(env, warehouse, sim_print_rate))

# generate mock orders to processed by the simulation
orders_source = generate_order_source()
# generate process to recieve all orders
env.process(order_reciever(env, warehouse, orders_source))

# generate process to manage worker schedule in the warehouse
env.process(shift_manager(env, warehouse))

# add process to write out logs to file at a specified rate
if warehouse.logging:
    env.process(write_logs(env, warehouse, sim_run_name, sim_log_save_rate))

# start time used to track simulation run time
start = time.time()

# ***** Run simulation ************************************
env.run(until=sim_until)

# calculate and print simulation total run time
end = time.time()
print(f'ran sim until {sim_until}, time to run: {end-start}')

# save logs to disk one last time
warehouse.write_sim_logs(env, sim_run_name)
# calculate and save final results to disk
warehouse.write_final_results_log(env, sim_run_name)