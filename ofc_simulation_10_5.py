import enum
import time
import math
import simpy
import random
import datetime
import pandas as pd

# TODO: Handle Tuesdays (probably just through parameters)

#------------------------------------------------------------------------------#
# Class Definitions
#------------------------------------------------------------------------------#

"""
CustomerOrderStatus enum values represent the state of orders as they proceed
through the fullfillment center operations flow.
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
CustomerOrder objects represent an order processed by the fullfillment center.
"""
class CustomerOrder:
    def __init__(self, env, warehouse, idx, order_details):
        """ __init__

        Args:
            env (simpy.Environment): simulation environment
            warehouse (FullfillmentCenter): manages state of the facility
            idx (int): unique identifier index
            order_details (dict): defines order requirements
        """
        # order will be cancelled when age hits order expiration (72 hours)
        self.ORDER_EXPIRATION = 72*60*60

        # order detail properties
        self.idx = idx
        # TODO: QUESTION: 'OrderId' from csv, do we need it? [no]
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

        # order status represents state of the order
        self.status = CustomerOrderStatus.UNPROCESSED
    
    def get_lost_sales_penalty(self, env, warehouse):
        return (
            self.qty_tshirt*warehouse.unit_lost_sales_penalty['tshirt'] +
            self.qty_hoodie*warehouse.unit_lost_sales_penalty['hoodie'] +
            self.qty_spants*warehouse.unit_lost_sales_penalty['spants'] +
            self.qty_sneaks*warehouse.unit_lost_sales_penalty['sneaks']
        )

    def get_gross_profit(self, env, warehouse):
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

"""
PackingStation objects represent packing stations installed at the fullfillment
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
            warehouse (FullfillmentCenter): manages state of the facility
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
        fullfill an order.

        Args:
            env (simpy.Environment): simulation environment
            order (CustomerOrder): order to check inventory for
        Return:
            bool: 1 if there is enough inventory to fullfill order, otherwise 0
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
            warehouse (FullfillmentCenter): manages state of the facility
            order (CustomerOrder): order to pickup inventory for
            name (str): name to identify associated picker
        """
        message = f"\torder {order.idx} >> picked up by {name}: "
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
            message = message + f"{order.qty_tshirt} tshirt "
        if order.qty_hoodie > 0:
            order.allocated_hoodie = order.allocated_hoodie + order.qty_hoodie
            yield self.bin2.avail_hoodie.get(order.qty_hoodie)
            bin_path.append(self.bin2.location)
            message = message + f"{order.qty_hoodie} hoodie "
        if order.qty_spants > 0:
            order.allocated_spants = order.allocated_spants + order.qty_spants
            yield self.bin3.avail_spants.get(order.qty_spants)
            bin_path.append(self.bin3.location)
            message = message + f"{order.qty_spants} spants "
        if order.qty_sneaks > 0:
            order.allocated_sneaks = order.allocated_sneaks + order.qty_sneaks
            yield self.bin4.avail_sneaks.get(order.qty_sneaks)
            bin_path.append(self.bin4.location)
            message = message + f"{order.qty_sneaks} sneaks "
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
        message = f"{env.now}:" + message + f"...pickup time {pickup_time}"
        # print(message)

    def stow_inventory(self, env, warehouse, product_type, amount, name):
        """ Stow inventory process generator for designated inventory policy. 
        During lifetime will generate put() request events from stowing 
        inventory in containers.
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FullfillmentCenter): manages state of the facility
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

        # print(f'{env.now}:\t stower {name} stowed {amount} {product_type} in {total_stow_time} seconds')

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
        fullfill an order.

        Args:
            env (simpy.Environment): simulation environment
            order (CustomerOrder): order to check inventory for
        Return:
            bool: 1 if there is enough inventory to fullfill order, otherwise 0
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
            warehouse (FullfillmentCenter): manages state of the facility
            order (CustomerOrder): order to pickup inventory for
            name (str): name to identify associated picker
        """
        message = f"\torder {order.idx} >> picked up by {name}: "

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

            # calculate num of sweatpants to get from current bin
            amount_spants = order.qty_spants - order.allocated_spants
            spants_get_amount = 0
            spants_level = current_bin.avail_spants.level
            if amount_spants > 0 and spants_level > 0:
                spants_get_amount = min(spants_level, amount_spants)
                # allocate sweatpants to the customer order
                order.allocated_spants += spants_get_amount

            # calculate num of sneakers to get from current bin
            amount_sneaks = order.qty_sneaks - order.allocated_sneaks
            sneaks_get_amount = 0
            sneaks_level = current_bin.avail_sneaks.level
            if amount_sneaks > 0 and sneaks_level > 0:
                sneaks_get_amount = min(sneaks_level, amount_sneaks)
                # allocate sneakers to the customer order
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

            # TODO: QUESTION: Document says pick a random adjacent bin, does that mean a picker can actually go back and forth between two bins multiple times?
            
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
        message = f"{env.now}:" + message + f"...pickup time {pickup_time}"
        # print(message)

    def stow_inventory(self, env, warehouse, product_type, amount, name):
        """ Stow inventory process generator for random inventory policy. 
        During lifetime will generate put() request events from stowing 
        inventory in containers. Inventory is stored in order 1->2->3->4
        
        Args:
            env (simpy.Environment): simulation environment
            warehouse (FullfillmentCenter): manages state of the facility
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

        # print(f'{env.now}:\t stower {name} stowed {amount} {product_type} in {total_stow_time} seconds')

"""
FullfillmentCenter objects connect the different components of a simulation by
tracking shared variables and offering helper functions.
"""
class FullfillmentCenter:
    def __init__(self, env):
        """ __init___

        Args:
            env (simpy.Environment): simulation environment
        """
        self.env = env

        # conceptual model givens
        self.initial_qtys = {
            'tshirt':10000,
            'hoodie':5000,
            'spants':5000,
            'sneaks':3333}
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
        
        #=======================================================================
        # DECISION: intialize inventory storage with designated or random policy
        #=======================================================================
        #self.inventory = DesignatedInventoryStorage(env, self.initial_qtys)
        self.inventory = RandomInventoryStorage(env, self.initial_qtys)

        #=======================================================================
        # DECISION: static delivery schedule over 52 weeks
        #=======================================================================
        self.inbound_delivery_daily = {
            'Monday':   {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Tuesday':  {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Wednesday':{'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Thursday': {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Friday':   {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Saturday': {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000},
            'Sunday':   {'tshirt':1000,'hoodie':1000,'spants':1000,'sneaks':1000}}
        # use daily delivery schedule to calculate a weekly schedule
        self.inbound_delivery_weekly = {
            'tshirt':0,
            'hoodie':0,
            'spants':0,
            'sneaks':0}
        for day in self.inbound_delivery_daily:
            self.inbound_delivery_weekly['tshirt'] = (
                self.inbound_delivery_weekly['tshirt'] +
                self.inbound_delivery_daily[day]['tshirt']) 
            self.inbound_delivery_weekly['hoodie'] = (
                self.inbound_delivery_weekly['hoodie'] +
                self.inbound_delivery_daily[day]['hoodie'])
            self.inbound_delivery_weekly['spants'] = (
                self.inbound_delivery_weekly['spants'] +
                self.inbound_delivery_daily[day]['spants'])
            self.inbound_delivery_weekly['sneaks'] = (
                self.inbound_delivery_weekly['sneaks'] +
                self.inbound_delivery_daily[day]['sneaks'])          
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

        #=======================================================================
        # DECISION: shift schedule for workers (pickers, packers, and stowers) 
        #=======================================================================
        self.shift_schedule = {}
        for i in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
            self.shift_schedule[i] = {
                'morning': {
                    'num_pickers': 5, 
                    'num_stowers': 2, 
                    'num_packers': 6},
                'afternoon': {
                    'num_pickers': 2, 
                    'num_stowers': 2, 
                    'num_packers': 6},
                'evening': {
                    'num_pickers': 2, 
                    'num_stowers': 2, 
                    'num_packers': 6}}
        # 8 hour shifts
        self.shift_length = 8*60*60
        # set initial shift to 'evening' as the simulation will begin with a
        # shift change from evening to morning
        self.current_shift = 'evening'

        #=======================================================================
        # DECISION: set number of packing stations and install them
        #=======================================================================
        self.num_packing_station = 6
        self.packing_stations = {}
        for i in range(1, self.num_packing_station+1):
            self.packing_stations[i] = PackingStation(env, i)

        # create Store object to handle recieved orders
        self.order_store = simpy.Store(env)

        #=======================================================================
        # KPI Tracking
        #=======================================================================
        self.orders_shipped = 0
        self.orders_cancelled = 0
        self.orders_discarded = 0

        self.gross_profit = 0

        self.delivery_expense = 0
        self.delivery_expense_returns = 0

        self.labor_expense = 0
        self.labor_expense_overtime = 0

        self.lost_sales_penalty = 0

        self.fixed_cost_facilities = 5000000
        self.fixed_cost_packing_stations = self.num_packing_station*50000
        
        # track total items of each type from inventory parking to shipped
        self.inventory_tracker = InventoryBin(env, 1, {
            'tshirt':0,
            'hoodie':0,
            'spants':0,
            'sneaks':0})
        self.inventory_holding_cost = 0

    def remove_from_inventory_tracker(self, env, order):
        if order.allocated_tshirt > 0:
            self.inventory_tracker.get_product_container('tshirt').get(order.allocated_tshirt)
        if order.allocated_hoodie > 0:
            self.inventory_tracker.get_product_container('hoodie').get(order.allocated_hoodie)
        if order.allocated_spants > 0:
            self.inventory_tracker.get_product_container('spants').get(order.allocated_spants)
        if order.allocated_sneaks > 0:
            self.inventory_tracker.get_product_container('sneaks').get(order.allocated_sneaks)

    def get_optimal_packing_station_queue(self):
        """ Return packing station with the least amount of orders waiting to be completed. If multiple packing stations 
        have the same amount of orders waiting to be completed, then select on randomly.

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

    def get_datetime(self):
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
            start_date_in_seconds + self.env.now
            ).astimezone(datetime.timezone.utc)
  
#------------------------------------------------------------------------------#
# Process Generators
#------------------------------------------------------------------------------#

def kpi_logger(env, warehouse):
    while True:
        wait = 28800
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

        yield env.timeout(wait)

def holding_cost_monitor(env, warehouse):
    while True:
        # calculate holding cost for a single time step
        tshirt_holding_cost = warehouse.inventory_tracker.avail_tshirt.level*(warehouse.unit_holding_rate_per_timestep['tshirt'])
        hoodie_holding_cost = warehouse.inventory_tracker.avail_hoodie.level*(warehouse.unit_holding_rate_per_timestep['hoodie'])
        spants_holding_cost = warehouse.inventory_tracker.avail_spants.level*(warehouse.unit_holding_rate_per_timestep['spants'])
        sneaks_holding_cost = warehouse.inventory_tracker.avail_sneaks.level*(warehouse.unit_holding_rate_per_timestep['sneaks'])
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
        warehouse (FullfillmentCenter): manages state of the facility
        freq (str): specify 'daily' or 'weekly' shipment delivery frequency
    """
    # calulate first inbound recieving time (9:00 AM)
    initial_wait = 9*60*60

    # set delivery frequency for the warehouse
    warehouse.delivery_frequency = freq

    # simulate wait until first shipment is delivered
    yield env.timeout(initial_wait)

    # setup recieving dock for daily or weekly deliveries
    if freq == 'daily':
        weekday = warehouse.get_datetime().strftime("%A")
        shipment_schedule = warehouse.inbound_delivery_daily[weekday]
        wait = 24*60*60
    elif freq == 'weekly':
        shipment_schedule = warehouse.inbound_delivery_weekly
        wait = 7*24*60*60

    # continuously run recieving dock process until simulation ends
    while True:
        # incur delivery fee
        warehouse.delivery_expense += warehouse.delivery_fee[freq]

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
            inbound_hoodie = min(inbound_tshirt, divmod(product_allowed_weight, warehouse.unit_weight['hoodie'])[0])
            inbound_spants = min(inbound_tshirt, divmod(product_allowed_weight, warehouse.unit_weight['spants'])[0])
            inbound_sneaks = min(inbound_tshirt, divmod(product_allowed_weight, warehouse.unit_weight['sneaks'])[0])

        # recieve inbound shipment
        if inbound_tshirt > 0:
            yield warehouse.inbound_parking.avail_tshirt.put(inbound_tshirt)
            yield warehouse.inventory_tracker.avail_tshirt.put(inbound_tshirt)
        if inbound_hoodie > 0:
            yield warehouse.inbound_parking.avail_hoodie.put(inbound_hoodie)
            yield warehouse.inventory_tracker.avail_hoodie.put(inbound_hoodie)
        if inbound_spants > 0:
            yield warehouse.inbound_parking.avail_spants.put(inbound_spants)
            yield warehouse.inventory_tracker.avail_spants.put(inbound_spants)
        if inbound_sneaks > 0:
            yield warehouse.inbound_parking.avail_sneaks.put(inbound_sneaks)
            yield warehouse.inventory_tracker.avail_sneaks.put(inbound_sneaks)

        # print(f'{env.now}:\t============== inbound shipment recieved ==============')
        # print(f'\tinbound parking: tshirt: {warehouse.inbound_parking.avail_tshirt.level}')
        # print(f'\tinbound parking: hoodie: {warehouse.inbound_parking.avail_hoodie.level}')
        # print(f'\tinbound parking: spants: {warehouse.inbound_parking.avail_spants.level}')
        # print(f'\tinbound parking: sneaks: {warehouse.inbound_parking.avail_sneaks.level}')
        # print(f'\t=======================================================')

        # simulate wait time for next shipment
        yield env.timeout(wait)
        
def order_reciever(env, warehouse, orders_source): 
    """ Process generator for recieving customer orders 
        During lifetime will process each order as it arrives.
        
    Args:
        env (simpy.Environment): simulation environment
        warehouse (FullfillmentCenter): manages state of the facility
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
        # kick off process to monitor age of order and cancel when expired
        env.process(order_age_monitor(env, warehouse, new_order))
        # create a new put() request event to add order to warehouse store
        warehouse.order_store.put(new_order)

def order_age_monitor(env, warehouse, order):
    """ Process generator for monitoring a single order. Cancels order if it
    expires (i.e. customer cancels after 72 hours).

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FullfillmentCenter): manages state of the facility
        order (CustomerOrder): order to monitor
    """
    # simulate lifetime of the order
    yield env.timeout(order.ORDER_EXPIRATION)
    # cancel order if it has not been shipped
    if order.status != CustomerOrderStatus.SHIPPED:
        order.status = CustomerOrderStatus.CANCELLED
        # increment number of orders cancelled
        warehouse.orders_cancelled += 1
        # incur sales penalty
        warehouse.lost_sales_penalty += order.get_lost_sales_penalty(env, warehouse)
        # stop tracking inventory for holding cost
        warehouse.remove_from_inventory_tracker(env, order)
        # print(f'{env.now}:\tcancel order {order.idx}, age: {order.get_age(env)} (arrival time: {order.arrival_time})')

def shift_manager(env, warehouse):
    """ Process generator for managing all shifts. During lifetime (length
    of simulation) will continuously generate timeout() events to trigger shift
    changes. When a shift change occurs, shift_manager sends workers to work.

    Args:
        env (simpy.Environment): simulation environment
        warehouse (FullfillmentCenter): manages state of the facility
    """
    while True:
        starting_inventory_holding_cost = warehouse.inventory_holding_cost

        # get day of the week
        weekday = warehouse.get_datetime().strftime("%A")

        # change shift in the context of the warehouse
        last_shift = warehouse.current_shift
        if last_shift == 'morning': 
            warehouse.current_shift = 'afternoon'
        elif last_shift == 'afternoon': 
            warehouse.current_shift = 'evening'
        elif last_shift == 'evening': 
            warehouse.current_shift = 'morning'
        print(f'-----\tshift change: {last_shift} to {weekday} {warehouse.current_shift}\t@ {warehouse.get_datetime()} -----')

        # send pickers to work
        for i in range(1, warehouse.shift_schedule[weekday][warehouse.current_shift]['num_pickers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new picker
            env.process(worker_shift(env, warehouse, name, 'picker'))
        # send stowers to work
        for i in range(1, warehouse.shift_schedule[weekday][warehouse.current_shift]['num_stowers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new stower
            env.process(worker_shift(env, warehouse, name, 'stower'))
        # send packers to work
        for i in range(1, warehouse.shift_schedule[weekday][warehouse.current_shift]['num_packers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            # add worker shift process to the environment for a new packer
            env.process(worker_shift(env, warehouse, name, 'packer'))

        # simulate wait time until next shift change
        yield env.timeout(warehouse.shift_length)

        shift_inventory_holding_cost = warehouse.inventory_holding_cost-starting_inventory_holding_cost
        # print(f'{env.now}:\tshift holding cost: {shift_inventory_holding_cost}')

def worker_shift(env, warehouse, name, worker_type):
    """ Process generator for managing individual shift of a worker. During 
    lifetime generates processes specific to the specified worker type. Manages
    length of the shift and sends workers home when their shift is over. If the
    work is still working at the end of the shift, they will finish their task
    and book overtime before heading home. 
    """
    # start worker's shift
    # print(f'{env.now}:\t{name} {worker_type} starts shift')
    # calculate end of worker's shift
    end_shift_time = env.now + warehouse.shift_length

    # worker is now working
    working = True
    # packer station assignment intially 0 aka "no assignment"
    stationed_at = 0
    stations = warehouse.packing_stations

    # while worker is still working, continue working
    while working:
        # calculate remaining time in worker's shift
        remaining_time_in_shift = max(0, end_shift_time - env.now)
        # if worker's shift is over, send worker home, otherwise perform task
        if env.now >= end_shift_time:
            working = False
            # calculate overtime
            overtime = env.now - end_shift_time
            # free up packing station when packer leaves it
            if worker_type == 'packer' and stationed_at != 0:
                # print(f'{env.now}:\t packing station {stationed_at} released by packer {name}')
                # TODO: HACK: can't figure out how to release, so just replacing the slot Resource in the PackingStation object with a new one with capcity 1
                stations[stationed_at].slots = simpy.Resource(env, capacity=1)

            warehouse.labor_expense += (warehouse.hourly_wage*warehouse.shift_length/60/60)
            warehouse.labor_expense_overtime += (overtime*(warehouse.hourly_wage/60/60))
            # print(f'{env.now}:\t{name} {worker_type} heads home, overtime: {overtime}')
        else:
            if worker_type == 'stower':
                # generate stower process
                yield env.process(stower(env, warehouse, name)) 
            elif worker_type == 'picker':
                # generate picker process
                yield env.process(picker(env, warehouse, name))
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
                                # print(f'{env.now}:\t{name} stower is assigned to {i}')
                                stationed_at = i
                if stationed_at == 0:
                    # packer not stationed at a packing station, remain idle
                    yield env.timeout(1)
                else:
                    # generate packer process
                    yield env.process(packer(
                        env, warehouse, stationed_at, name))

def picker(env, warehouse, name):
    """ 

    """
    if len(warehouse.order_store.items) > 0:
        # attempt to get an order from the order_store
        get_order = yield warehouse.order_store.get()
        # if order is available, work on it
        #if get_order.triggered:
        order = get_order#.value
        if order.status != CustomerOrderStatus.CANCELLED:
            # if order has not been cancelled, run picker item pickup service
            # print(f'{env.now}:\t{name} picker got order {order.idx} from store with arrival time: {order.arrival_time}')
            # check if order can be fullfilled with current inventory, if not, discard order, otherwise pick up for order
            if warehouse.inventory.check_inventory(env, order):
                # pickup inventory for order
                yield env.process(warehouse.inventory.pickup_inventory(env, warehouse, order, name))
                # wait time to send picked products from the picking station to the packing station before starting another trip
                yield env.timeout(30)
                if order.status != CustomerOrderStatus.CANCELLED:
                    order.status = CustomerOrderStatus.WAITING_TO_PACK
                    warehouse.get_optimal_packing_station_queue().put(order)
                    # print(f'{env.now}:\torder {order.idx} placed on insta-conveyor to packing station ...{name} picker released')
            else:
                # discard order due to lack of available inventory
                order.status = CustomerOrderStatus.DISCARDED
                # increment number of discarded orders
                warehouse.orders_discarded += 1
                # incur sales penalty
                warehouse.lost_sales_penalty += order.get_lost_sales_penalty(env, warehouse)
                # stop tracking inventory for holding cost
                warehouse.remove_from_inventory_tracker(env, order)
                # print(f'{env.now}:\torder {order.idx} discarded, not enough available inventory ...{name} picker released')
    else:
        # no order is available to process, wait until next timestep to check order_store again
        yield env.timeout(1)
        # TODO: Log idle time? Do this for all workers, will want to know idle per shift

def stower(env, warehouse, name):
    """ 

    """
    # get product with max remaining work
    max_work_product = warehouse.inbound_parking.get_max_work_product_type(env, warehouse)
    product_type = max_work_product['product_type']
    if product_type != 'None':
        product_container = warehouse.inbound_parking.get_product_container(product_type)
        max_amount = math.floor(12/warehouse.unit_weight[product_type])
        amount = min(max_amount, product_container.level)
        # print(f'{env.now}:\tstower {name} starts picking up {amount} {product_type} from inbound parking')
        yield product_container.get(amount)
        yield env.timeout(120) # time to pick up from inbound parking
        # print(f'{env.now}:\tstower {name} picked up {amount} {product_type} from inbound parking, starts stowing')
        yield env.process(warehouse.inventory.stow_inventory(env, warehouse, product_type, amount, name))
    else:
        # no inbound work remaining to process, check again next step
        yield env.timeout(1)

def packer(env, warehouse, assigned_station, name):
    """ 

    """
    order_queue = warehouse.packing_stations[assigned_station].queue
    if len(order_queue.items) > 0:
        order = yield order_queue.get()
        if order.status == CustomerOrderStatus.WAITING_TO_PACK:
            # print(f'{env.now}: packer {name} >>> order {order.idx} is available to pack at station {assigned_station}, start packing')
            pack_time = (
                30 + # base time to pack
                order.allocated_tshirt*10 + # time to pack units
                order.allocated_hoodie*10 + # time to pack units
                order.allocated_spants*10 + # time to pack units
                order.allocated_sneaks*10   # time to pack units
            )
            yield env.timeout(pack_time)
            order.status = CustomerOrderStatus.SHIPPED
            # increment number of orders shipped
            warehouse.orders_shipped += 1
            # book profit!
            warehouse.gross_profit += order.get_gross_profit(env, warehouse)
            # stop tracking inventory for holding cost
            warehouse.remove_from_inventory_tracker(env, order)
            
            # print(f'{env.now}:\t packer {name} at station {assigned_station} packed and shipped order {order.idx}!')
        else:
            # order is not waiting to pack, this should never happen, check again next timestep
            yield env.timeout(1)
    else:
        # no order available, check again next timestep
        yield env.timeout(1)
    
#------------------------------------------------------------------------------#
# Run Simulation 
# TODO: Turn the simulation run into a class or function so it can be called 
#       repeatedly with different configurations. i.e. 
#       sim1 = Simulation(orders, shift_schedule, inventory_type)
#       sim2 = Simulation(orders, shift_schedule2, inventory_type2)
#       sim1.runSimulation(until=sim_length)
#       sim2.runSimulation(until=sim_length2)
#------------------------------------------------------------------------------#

# for comparing results easily
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# environment is the clock (event queue)
env = simpy.Environment()

# warehouse has configurations, components, and kpis
warehouse = FullfillmentCenter(env)

# generate process to handle inbound recieving
# DECISION: specify weekly or daily shipments
env.process(inbound_recieving_dock(env, warehouse, 'daily'))

# calculate holding cost every timestep
env.process(holding_cost_monitor(env, warehouse))

# TODO: turn into a logger instead of printer
env.process(kpi_logger(env, warehouse))

sim_until = 86401*7
#===============================================================================
# Create list of order details
orders = {}
for i in range(1,divmod(sim_until,10)[0]):
    orders[i] = {
        'OrderTimeInSec': 10*i, 
        'QtyShirt': random.randint(1,2), 
        'QtyHoodie': random.randint(1,2), 
        'QtySweatpants': random.randint(1,2), 
        'QtySneakers': random.randint(1,2)
    }
# Create list of CustomerOrder objects from order details
orders_source = []
for idx in orders:
    orders_source.append(CustomerOrder(env, warehouse, idx, orders[idx]))
#===============================================================================

# generate process to recieve all orders
env.process(order_reciever(env, warehouse, orders_source))

# generate process to manage worker schedule in the warehouse
env.process(shift_manager(env, warehouse))

start = time.time()

## Run simulation
env.run(until=sim_until)

end = time.time()
print(f'ran sim until {sim_until}, time to run: {end-start}')