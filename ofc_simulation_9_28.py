import enum
import simpy
import random
import datetime

#-------------------------------------------------------------------------------------#
# Class Definitions
#-------------------------------------------------------------------------------------#

class CustomerOrderStatus(enum.Enum):
    UNPROCESSED     = 1,
    ARRIVED         = 2,
    FILLED          = 3,
    WAITING_TO_PACK = 4,
    PACKED          = 5,
    SHIPPED         = 6,
    DISCARDED       = 7,
    CANCELLED       = 8

class CustomerOrder:
    def __init__(self, env, warehouse, idx, order_details):
        # pseudo constant TODO: consider making a real constant with a getter function
        self.ORDER_EXPIRATION = 500 # 72 hours
        # order detail properties
        self.idx = idx
        # TODO: missing the order id
        self.arrival_time = order_details['OrderTimeInSec']
        self.qty_tshirt = order_details['QtyShirt']
        self.qty_hoodie = order_details['QtyHoodie']
        self.qty_spants = order_details['QtySweatpants']
        self.qty_sneaks = order_details['QtySneakers']
        # order state properties
        self.age = 0
        self.status = CustomerOrderStatus.UNPROCESSED
        
    def get_age(self, env):
        age = env.now - self.arrival_time
        return age

    def get_gross_profit(self, env, warehouse):
        gross_profit = (
            self.qty_tshirt * warehouse.gross_profit['tshirt'] + 
            self.qty_hoodie * warehouse.gross_profit['hoodie'] + 
            self.qty_spants * warehouse.gross_profit['spants'] +
            self.qty_sneaks * warehouse.gross_profit['sneaks']
        )
        return gross_profit

    def get_lost_sales_penalty(self, env, warehouse):
        penalty = (
            self.qty_tshirt * warehouse.lost_sales_penalty_values['tshirt'] + 
            self.qty_hoodie * warehouse.lost_sales_penalty_values['hoodie'] + 
            self.qty_spants * warehouse.lost_sales_penalty_values['spants'] +
            self.qty_sneaks * warehouse.lost_sales_penalty_values['sneaks']
        )
        return penalty

class InventoryBin:
    def __init__(self, env, bin_location, initial_qtys):
        self.location = bin_location
        self.avail_tshirt = simpy.Container(env, init=initial_qtys['tshirt'])
        self.avail_hoodie = simpy.Container(env, init=initial_qtys['hoodie'])
        self.avail_spants = simpy.Container(env, init=initial_qtys['spants'])
        self.avail_sneaks = simpy.Container(env, init=initial_qtys['sneaks'])

class SimpleInventoryStorage:
    def __init__(self, env, initial_qtys):
        self.initial_qtys = initial_qtys
        # setup discreate inventory bins, one for each product type
        self.bin1 = InventoryBin(env, 1, {'tshirt':initial_qtys['tshirt'],'hoodie':0,'spants':0,'sneaks':0})
        self.bin2 = InventoryBin(env, 2, {'tshirt':0,'hoodie':initial_qtys['hoodie'],'spants':0,'sneaks':0})
        self.bin3 = InventoryBin(env, 3, {'tshirt':0,'hoodie':0,'spants':initial_qtys['spants'],'sneaks':0})
        self.bin4 = InventoryBin(env, 4, {'tshirt':0,'hoodie':0,'spants':0,'sneaks':initial_qtys['sneaks']})

    # check if there is enough inventory in storage to fullfill an order
    def check_inventory(self, env, order):
        if order.qty_tshirt > self.bin1.avail_tshirt.level:
            return 0
        if order.qty_hoodie > self.bin2.avail_hoodie.level:
            return 0
        if order.qty_spants > self.bin3.avail_spants.level:
            return 0
        if order.qty_sneaks > self.bin4.avail_sneaks.level:
            return 0
        # there is enough inventory to fullfill the order
        return 1 

    # pickup inventory process generator
    def pickup_inventory(self, env, warehouse, order, name):
        message = f"\torder {order.idx} >> picked up by {name}: "
        bin_path = []
        # simple picker service uses discrete one-product-type-per-bin inventory storage
        if order.qty_tshirt > 0:
            # allocate tshirts (remove from bin1)
            yield warehouse.inventory.bin1.avail_tshirt.get(order.qty_tshirt)
            bin_path.append(warehouse.inventory.bin1.location)
            message = message + f"{order.qty_tshirt} tshirt "
        if order.qty_hoodie > 0:
            # allocate hoodies (remove from bin2)
            yield warehouse.inventory.bin2.avail_hoodie.get(order.qty_hoodie)
            bin_path.append(warehouse.inventory.bin2.location)
            message = message + f"{order.qty_hoodie} hoodie "
        if order.qty_spants > 0:
            # allocate spants (remove from bin3)
            yield warehouse.inventory.bin3.avail_spants.get(order.qty_spants)
            bin_path.append(warehouse.inventory.bin3.location)
            message = message + f"{order.qty_spants} spants "
        if order.qty_sneaks > 0:
            # allocate sneaks (remove from bin4)
            yield warehouse.inventory.bin4.avail_sneaks.get(order.qty_sneaks)
            bin_path.append(warehouse.inventory.bin4.location)
            message = message + f"{order.qty_sneaks} sneaks "

        start_bin_location = bin_path[0]
        end_bin_location = bin_path[len(bin_path)-1]
        pickup_time = (
            120 + # time to travel from picking station to first bin
            order.qty_tshirt*10 + # time to pick up indvidual items
            order.qty_hoodie*10 + # time to pick up indvidual items
            order.qty_spants*10 + # time to pick up indvidual items
            order.qty_sneaks*10 + # time to pick up indvidual items
            (end_bin_location - start_bin_location)*60 + # time to travel between bins
            120 # time to travel back to picking station
        )
        yield env.timeout(pickup_time)
        order.status = CustomerOrderStatus.FILLED
        message = f"{env.now}:" + message + f"...pickup time {pickup_time}"
        print(message)

class RandomInventoryStorage:
    def __init__(self, env, initial_qtys):
        # setup mixed inventory bins, splitting products to be stores 25% in each bin (remainders go into bin4)
        tshirt_split, tshirt_remain = divmod(initial_qtys['tshirt'],4)
        hoodie_split, hoodie_remain = divmod(initial_qtys['hoodie'],4)
        spants_split, spants_remain = divmod(initial_qtys['spants'],4)
        sneaks_split, sneaks_remain = divmod(initial_qtys['sneaks'],4)
        self.bin1 = InventoryBin(env, 1, {'tshirt':tshirt_split,'hoodie':hoodie_split,'spants':spants_split,'sneaks':sneaks_split})
        self.bin2 = InventoryBin(env, 2, {'tshirt':tshirt_split,'hoodie':hoodie_split,'spants':spants_split,'sneaks':sneaks_split})
        self.bin3 = InventoryBin(env, 3, {'tshirt':tshirt_split,'hoodie':hoodie_split,'spants':spants_split,'sneaks':sneaks_split})
        self.bin4 = InventoryBin(env, 4, {
            'tshirt':tshirt_split + tshirt_remain,
            'hoodie':hoodie_split + hoodie_remain,
            'spants':spants_split + spants_remain,
            'sneaks':sneaks_split + sneaks_remain
            })

    # check if there is enough inventory in storage to fullfill an order
    def check_inventory(self, env, order):
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
        # there is enough inventory to fullfill the order
        return 1 

class FullfillmentCenter:
    def __init__(self, env):

        # property givens from conceptual model
        self.initial_qtys = {'tshirt':10000,'hoodie':5000,'spants':5000,'sneaks':3333}
        self.gross_profit = {'tshirt':4,'hoodie':10,'spants':10,'sneaks':20}
        self.lost_sales_penalty_values = {'tshirt':1,'hoodie':6,'spants':6,'sneaks':10}

    
        self.order_store = simpy.Store(env)
        self.inventory = SimpleInventoryStorage(env, self.initial_qtys)

        # setup the shifts 
        # TODO: add Weekday context to shifts
        # TODO: it may make more sense for each shift to be an instance of new "shift" class 
        #       similar in nature to CustomerOrder class
        self.shift_length = 100 #8*60*60
        self.shifts = {
            'morning': {'num_pickers': 5},
            'afternoon': {'num_pickers': 2},
            'evening': {'num_pickers': 2}
        }
        self.current_shift = 'morning'

        self.num_packing_station = 5
        self.packing_stations = {}
        for i in range(1, self.num_packing_station+1):
            self.packing_stations[i] = simpy.Store(env)

        # kpi tracking
        self.lost_sales_penalties_incurred = 0

    # return the packing station store that has the fewest items in the queue
    def get_optimal_packing_station(self):
        # choose packing station 1 by default
        packing_station_id = 1
        min_orders_in_queue = len(self.packing_stations[1].items)
        # choose packing station with the least number of orders in queue
        for i in self.packing_stations:
            if i > 1:
                orders_in_queue = len(self.packing_stations[i].items)
                if orders_in_queue < min_orders_in_queue:
                    min_orders_in_queue = orders_in_queue
                    packing_station_id = i
        # return packing station store
        print(f'--------------------------------------------------putting an order on the packing_station queue at {packing_station_id}')
        return self.packing_stations[packing_station_id]

    # get the human readable datetime of the warehouse as it is "now"
    # TODO: as it stands, this doesn't have to be a function of the warehouse, just the simulation
    #       leave it here? modify it so the warehouse takes a start date and it is used? or move it into the simulation loop
    def get_datetime(self):
        # datetime package start time: Wednesday, December 31, 1969 04:00:00
        start_date = datetime.datetime(2020, 10, 21, 0, 0, tzinfo=None)
        # subtract package start date from our start date and get seconds
        start_date_in_seconds = (start_date-datetime.datetime(1969,12,31,0,0,tzinfo=None)).total_seconds()
        # return simulation's current mock datetime
        return datetime.datetime.fromtimestamp(start_date_in_seconds + env.now).astimezone(datetime.timezone.utc).strftime("%A, %B %d, %Y %I:%M:%S")
        
#-------------------------------------------------------------------------------------#
# Process Generators
#-------------------------------------------------------------------------------------#

def order_reciever(env, warehouse, orders_source):  
    # process each order from the order source one at a time (until no orders are left)
    while len(orders_source) > 0:
        # pop first order from orders source
        new_order = orders_source.pop(0)
        # calulate when order will arrive relative to now
        wait = max(0, new_order.arrival_time - env.now)
        # wait for order to arrive
        yield env.timeout(wait)
        new_order.status = CustomerOrderStatus.ARRIVED
        # kick off process to monitor age of order and cancel when expired
        env.process(order_age_monitor(env, warehouse, new_order))
        # create a new StoreGet event to add order to warehouse store
        warehouse.order_store.put(new_order)

def order_age_monitor(env, warehouse, order):
    yield env.timeout(order.ORDER_EXPIRATION)
    # cancel order if it has not been shipped
    if order.status != CustomerOrderStatus.SHIPPED:
        order.status = CustomerOrderStatus.CANCELLED
        # TODO: book lost sales penalty for order
        print(f'{env.now}:\tcancel order {order.idx}, age: {order.get_age(env)} (arrival time: {order.arrival_time})')

def shift_manager(env, warehouse):
    # TODO: add Weekday context to shifts, maybe shifts should be objects or named tuples

    # TODO: handle first shift
    #
    # Figure out why sending pickers here breaks the whole simulation...
    #
    # send pickers to work
    # for i in range(1, warehouse.shifts[warehouse.current_shift]['num_pickers']+1):
    #     name = f'{env.now}{warehouse.current_shift}{i}'
    #     env.process(worker_shift(env, warehouse, name, 'picker'))

    while True:
        # continuely manage shift changes until simulation ends
        yield env.timeout(warehouse.shift_length)
        # change shift in the context of the warehouse
        last_shift = warehouse.current_shift
        if last_shift == 'morning': 
            warehouse.current_shift = 'afternoon'
        elif last_shift == 'afternoon': 
            warehouse.current_shift = 'evening'
        elif last_shift == 'evening': 
            warehouse.current_shift = 'morning'
        print(f'-----\tshift change: {last_shift} to {warehouse.current_shift}\t@ {warehouse.get_datetime()} -----')

        # send pickers to work
        for i in range(1, warehouse.shifts[warehouse.current_shift]['num_pickers']+1):
            name = f'{env.now}{warehouse.current_shift}{i}'
            env.process(worker_shift(env, warehouse, name, 'picker'))

        # TODO: send stowers to work

        # TODO: send packers to work

def worker_shift(env, warehouse, name, worker_type):
        # start worker's shift
        print(f'{env.now}:\t{name} {worker_type} starts shift')
        # calculate end of worker's shift
        end_shift_time = env.now + warehouse.shift_length
        # worker is now working
        working = True
        # while worker is still working, continue working
        while working:
            # calculate remaining time in worker's shift
            remaining_time_in_shift = max(0, end_shift_time - env.now)
            # if worker's shift is over, send worker home, otherwise perform task
            if env.now >= end_shift_time:
                working = False
                overtime = env.now - end_shift_time
                # TODO: calculate cost or total time etc.
                print(f'{env.now}:\t{name} {worker_type} heads home, overtime: {overtime}')
            else:
                if worker_type == 'stower':
                    print('TODO: write stower processes')
                    # env.process(stower(env, warehouse, name)) 
                elif worker_type == 'picker':
                    # start picker process task
                    yield env.process(picker(env, warehouse, name))
                elif worker_type == 'packer':
                    print('TODO: packer processes')
                    # env.process(packer(env, warehouse, name))

def picker(env, warehouse, name):
        # attempt to get an order from the order_store
        get_order = warehouse.order_store.get()
        # if order is available, work on it
        if(get_order.triggered):
            order = get_order.value
            if order.status != CustomerOrderStatus.CANCELLED:
                # if order has not been cancelled, run picker item pickup service
                print(f'{env.now}:\t{name} picker got order {order.idx} from store with arrival time: {order.arrival_time}')
                # TODO: make sure this is working then go ahead and delete the next line and the service it references
                # yield env.process(simple_pickup_service(env, warehouse, order, name))
                # check if order can be fullfilled with current inventory, if not, discard order, otherwise pick up for order
                if warehouse.inventory.check_inventory(env, order):
                    # pickup inventory for order
                    yield env.process(warehouse.inventory.pickup_inventory(env, warehouse, order, name))
                    # wait time to send picked products from the picking station to the packing station before starting another trip
                    yield env.timeout(30)
                    order.status = CustomerOrderStatus.WAITING_TO_PACK
                    yield warehouse.get_optimal_packing_station().put(order)
                    print(f'{env.now}:\torder {order.idx} placed on inst-conveyor to packing station ...picker {name} released')
                else:
                    # discard order due to lack of available inventory
                    order.status = CustomerOrderStatus.DISCARDED
                    print(f'{env.now}:\torder {order.idx} discarded, not enough available inventory ...picker {name} released')
        else:
            # no order is available to process, wait until next timestep to check order_store again
            yield env.timeout(1)

#-------------------------------------------------------------------------------------#
### TODO: Processes not done being written
#-------------------------------------------------------------------------------------#

# TODO: once tested, use just "picker" instead of "picker and simple_pickup_service"
def simple_pickup_service(env, warehouse, order, name):
    # check if order can be fullfilled with current inventory, if not, discard order, otherwise pick up for order
    if warehouse.inventory.check_inventory(env, order):
        message = f"\torder {order.idx} >> picked up by {name}: "
        bin_path = []
        # simple picker service uses discrete one-product-type-per-bin inventory storage
        if order.qty_tshirt > 0:
            # allocate tshirts (remove from bin1)
            yield warehouse.inventory.bin1.avail_tshirt.get(order.qty_tshirt)
            bin_path.append(warehouse.inventory.bin1.location)
            message = message + f"{order.qty_tshirt} tshirt "
        if order.qty_hoodie > 0:
            # allocate hoodies (remove from bin2)
            yield warehouse.inventory.bin2.avail_hoodie.get(order.qty_hoodie)
            bin_path.append(warehouse.inventory.bin2.location)
            message = message + f"{order.qty_hoodie} hoodie "
        if order.qty_spants > 0:
            # allocate spants (remove from bin3)
            yield warehouse.inventory.bin3.avail_spants.get(order.qty_spants)
            bin_path.append(warehouse.inventory.bin3.location)
            message = message + f"{order.qty_spants} spants "
        if order.qty_sneaks > 0:
            # allocate sneaks (remove from bin4)
            yield warehouse.inventory.bin4.avail_sneaks.get(order.qty_sneaks)
            bin_path.append(warehouse.inventory.bin4.location)
            message = message + f"{order.qty_sneaks} sneaks "

        start_bin_location = bin_path[0]
        end_bin_location = bin_path[len(bin_path)-1]
        pickup_time = (
            120 + # time to travel from picking station to first bin
            order.qty_tshirt*10 + # time to pick up indvidual items
            order.qty_hoodie*10 + # time to pick up indvidual items
            order.qty_spants*10 + # time to pick up indvidual items
            order.qty_sneaks*10 + # time to pick up indvidual items
            (end_bin_location - start_bin_location)*60 + # time to travel between bins
            120 # time to travel back to picking station
        )
        yield env.timeout(pickup_time)
        order.status = CustomerOrderStatus.FILLED
        message = f"{env.now}:" + message + f"...pickup time {pickup_time}"
        print(message)

        # time to send picked products from the picking station to the packing station before
        # starting another trip
        yield env.timeout(30)
        order.status = CustomerOrderStatus.WAITING_TO_PACK
        yield warehouse.get_optimal_packing_station().put(order)
        print(f'{env.now}:\torder {order.idx} placed on inst-conveyor to packing station ...picker {name} released')

    else:
        # discard order due to lack of available inventory
        order.status = CustomerOrderStatus.DISCARDED
        print(f'{env.now}:\torder {order.idx} discarded, not enough available inventory ...picker {name} released')
    
    yield env.timeout(1)
# TODO: [STUB] implement stower
def stower(env, warehouse, name):
    
    # while there are still unstowed inventories
        # yield env.stower_service(env, warehouse, name, other params)

    # If there are no unstowed inventories, and it's not an afternoon shift (8-4), then there will
    # not be more inventory delivered this shift, book wasted time (end_of_shift - env.now)

    # placeholder so no debug error
    yield env.timeout(10)
# TODO: [STUB] implement stower service
def stower_service(env, warehouse, name, other_params):
    # calculate stowing time (round trip)
    stowing_time = 10

    # get items from inbound inventory containers
    # TODO: create inbound inventory containers
    # put items in inventories

    # placeholder so no debug error
    yield env.timeout(stowing_time)
# TODO: [STUB] implement packer
def packer(env, warehouse, name, packing_station):

    # remain idle until packing station is open (no other packer is already working at assigned packing station)
    # (still racking up work time/cost)
    ### This is confusing to me, why would we ever have more packers than packing stations?

    # if packing station is open, do stuff, otherwise wait
    # attempt to get an order from the assigned packing station queue
    #   if got order:
        # yield packing_service
    # else 
    #   wait until next timestep to check again

    # placeholder so no debug error
    yield env.timeout(10)
# TODO: [STUB] implement packing service
def packing_service(env, warehouse, order, name):
    time_to_pack = (
        30 + # base packing time
        order.qty_tshirt*10 + # time to pick up indvidual items
        order.qty_hoodie*10 + # time to pick up indvidual items
        order.qty_spants*10 + # time to pick up indvidual items
        order.qty_sneaks*10   # time to pick up indvidual items
    )
    yield env.timeout(time_to_pack)
    order.status = CustomerOrderStatus.PACKED
    # TODO: nothing happens in between these states?
    order. status = CustomerOrderStatus.SHIPPED
    # TODO: book profit and inventory holding costs

#-------------------------------------------------------------------------------------#
# Run Simulation 
# TODO: Turn the simulation run into a class or function so it can be called 
#       repeatedly with different configurations. i.e. 
#       sim1 = Simulation(orders, shift_schedule, inventory_type)
#       sim2 = Simulation(orders, shift_schedule2, inventory_type2)
#       sim1.runSimulation(until=sim_length)
#       sim2.runSimulation(until=sim_length2)
#-------------------------------------------------------------------------------------#

# for comparing results easily
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# environment is the clock (event queue)
env = simpy.Environment()

# warehouse has configurations, components, and kpis
warehouse = FullfillmentCenter(env)

# generate process to manage worker schedule in the warehouse
env.process(shift_manager(env, warehouse))

## Create list of order details
orders = {}
for i in range(1,100): # right now even a million doesn't take super long (total memory usage 1gb)
    orders[i] = {
        'OrderTimeInSec': 10*i, 
        'QtyShirt': random.randint(0,10), 
        'QtyHoodie': random.randint(0,10), 
        'QtySweatpants': random.randint(0,10), 
        'QtySneakers': random.randint(0,10)
    }

# Create list of CustomerOrder objects from order details
orders_source = []
for idx in orders:
    orders_source.append(CustomerOrder(env, warehouse, idx, orders[idx]))
# generate process to recieve all orders
env.process(order_reciever(env, warehouse, orders_source))

## Run simulation
env.run(until=1500)
