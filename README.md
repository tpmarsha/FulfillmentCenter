# Amazon Order Fulfillment Center Operations and Supply Chain Simulation

## Contributors
* Tim Marshall (tpmarsha)
* Jonathan Culbert (jonculbert)
* Thao Spraggins
* George Matthews

## Context
This project was implemented to compete with other CMU MSBA teams given a series of strict constraints/rules. The file  *ofc_fulfillment_rules.pdf* describes the problem in detail.

## Our Approach
Our team developed an optimized operations and supply chain management policy for a fulfillment center. After data analysis, we created a systems-level simulation to test different strategies for the center’s operations. Although complex, the comprehensive approach allows us to evaluate how the sub-operations within the center interact with each other. This readme covers our simulation architecture, initial exploratory analysis of the 52-week orders,and the following specific operations: 1) Inbound Receiving, 2) Storage, and 3) Outbound Processing.

### click to view full size diagrams
![diagram of simulation flow](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/sim_flow.PNG?raw=true)
![diagram of class relationships](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/relationships.PNG?raw=true)
![diagram of event generator functions](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/generators.PNG?raw=true)

## Orders and Capacity Exploration
*Demand Patterns*

Based on the 52-week orders data, we have uncovered the demand patterns for each item type. Understanding the demand patterns enables us to predict new orders and plan schedules for workers and the optimal shipment quantity. To generate new orders for testing, we explored the distribution of orders by different timeframes (i.e. month, week, day, hour) and item type. As shown in the figure below left, there are more orders on the weekends displayed in red (Friday to Sunday) with a small peak in the middle of the week. The line graphs display order quantities for each item; t-shirts are the most popular item by quantity ordered while sneakers are the least popular item. Interestingly, hoodies and sweatpants follow the same distribution - they seemingly complement each other in an outfit very well!

![item orders](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/item_orders.png?raw=true)
![order distribution](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/num_orders.png?raw=true)

*Worker Capacity*

With an objective to maximize the utilization rate, we analyzed the order distribution (above right) by hour to assist with the worker shift scheduling. Intuitively, there are less orders during 11:00 PM and 6:00 AM. With this information and utilization calculation, we reorganized the schedules to have less workers during the early morning shifts and more workers during busy shifts. The workers capacity analysis is also crucial in our decision making of inventory storage - random or designated. The storage policy impacts both the inbound and outbound operations, so the workers assignment heavily depends on which policy we choose. 
We also needed to consider how many units an average worker can handle for a better understanding of the workers’ capacity. Since the throughput rates for stower, picker, and packer operations vary, we identified the bottleneck and assigned more workers to longer duration tasks. For instance there are two major areas - inbound and outbound. Inbound receiving is limited to stower’s throughput rate of approximately 12 lbs of product per 400 seconds. For outbound, there are two potential bottlenecks with an average order of two t-shirts taking a picker 290 seconds and a packer only 50 seconds. In addition to the varied throughput rates, we would have to consider the number of workers based on our decision of weekly or daily delivery schedule as that would directly impact the stowers. 

## Order Generation
To test our system on a variety of order patterns, we needed to approximate the pattern found in the 52 weeks of order history data. For order arrival times, we first tested the simplest option: an exponential distribution. While the average arrival time clearly varied over time, within hour-long intervals, an exponential distribution fit well. The mean and standard deviation were approximately equal within each weekday-hour pair, which is a property of the exponential distribution, further supporting this hypothesis. Using 168 different parameters (one for each hour of each weekday) estimated from the history data, we simulated our order arrival times using an exponential distribution. Next, we turn our attention to the item frequencies within each order.

### Item Counts per Order:
![observed vs. simulated](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/observed_simulated.png?raw=true)

To simulate the number of each item that appears in each order, the Poisson distribution seemed like a natural choice. However, the item frequencies observed in the order history data differed from independent Poisson distributions in two ways: their variances were slightly less than their means (we’d expect them to be equal), and they exhibited negative correlations. Though puzzling at first, we were able to reproduce both of these effects by generating item frequencies with four independent Poisson distributions (one for each item type), then discarding orders that contained zero items. This discarding of empty orders created very similar properties in our simulated order data to those observed in the order history. We used the Poisson means 1.0, 0.5, 0.5, and 0.25 for t-shirts, hoodies, sweatpants, and sneakers, respectively.

## Inbound Receiving
We tested four different base policies for inbound receiving: daily versus weekly deliveries, and random versus designated storage. We also added “optimized” variants for the daily delivery options. “Unoptimized stock” means keeping the same baseline levels that were given in our initial inventory. “Optimized stock” means letting our initial inventory run down to a more cost-effective, but still safe, level. For weekly deliveries, we were always forced to optimize stock because the starting conditions of the simulation led to an unavoidable stockout during the first weekend.
 
![list of possible policies](https://github.com/tpmarsha/fulfillmentCenter/blob/master/images/policy.png?raw=true)

While designated storage saves approximately $4,000 per week in stower cost, we selected random storage with daily deliveries, as the additional cost of pickers when using the designated storage policy more than offset the cost advantage shown here. (We discuss the storage decision further in the next section.) Weekly deliveries would have saved $20,000 per week in delivery fees, but holding costs from the additional inventory levels required to safely use this strategy would more than offset these savings. Finally, optimized inventory levels saved approximately $22,000 per week compared to keeping the initial inventory levels in stock.
Stowers were scheduled during each day’s 4:00 PM to midnight shift, so they could spend their entire eight-hour shift stowing. Although this means that deliveries are left in the parking area for seven hours each day, this assignment avoids stowers being idle for the first hour of their shifts. Using this schedule, we achieved over 97% average stower utilization, with no unstowed inventory accumulating in the parking area. Because inbound deliveries are deterministic and fully known, we can approach 100% stower utilization without fear of capacity problems. If we had randomness in our delivery arrival times or quantities, such high utilization could cause long backups of inbound inventory, and we would require more stowers.

We note here that there is an obvious option that is omitted: the base stock policy. This is seemingly the optimal choice in this scenario. However, the rules of the simulation require us to specify our entire year of orders ahead of time, so it is not possible to implement the base stock policy. The newsvendor model, likewise, cannot be applied to this scenario. Unsold stock is not discarded at the end of the day, and there is sequence risk associated with maintaining sufficient inventory levels over the course of our 52 week simulation. Because of this, we reached our optimal storage levels empirically via repeated simulation.

## Outbound Processing
*Picking Operations*

Since the orders vary throughout weekdays and hours, we sought to compare the optimal number of pickers between the designated and random storage policies. While the designated policy requires fewer stowers than random storage, we would need to assign more pickers under this policy, which needs 234 pickers weekly. Under the random storage policy, pickers have better utilization rates since they do not necessarily need to travel between storage bins. With better utilization, we only need 189 pickers weekly, which amounts to $8,100 in savings weekly. Since this is greater than the additional stower cost, this supports the random storage policy over the designated option. The assignment for pickers is detailed in the figure below, which highlights more pickers assigned to shifts between 8:00 AM and 12:00 AM. (“Morning” is midnight to 8:00 AM, “Afternoon” is 8:00 AM to 4:00 PM, and “Evening” is 4:00 PM to midnight.)
 
*Packing Operations*

The packers can run the same schedule every week as the orders are mostly consistent from week to week. Since each packing station costs $50K over 52 weeks with only one packer working a station, we focussed on the number of packing stations at any given time to be at 2 stations. The fixed cost of packing stations thus comes to $100K and the number of stations stays the same throughout the simulation. The station with the least amount of orders would be assigned the queue and if both stations were to have the same amount of orders, then queue assignment is meant to be random. Keeping daily schedules and random storage policy in mind, the most optimal utilization was at 2 packers/shift for most weekdays, except on Mondays and Saturdays, when we allocate 1 packer/shift.

## Simulation Program Architecture
To best optimize our fulfillment center policies, we developed a “master” program model of the entire conceptual model. Even on paper this was pretty complex and we knew we did not want to implement both our model and a custom event handling system at the same time. We researched a few frameworks and were fortunate to find SimPy, a process-based discrete-event simulation framework based on standard Python. SimPy is lightweight, open source, and uses discrete event queuing to simulate parallel processes without multithreading. In implementing our simulation we leverage three core components of the SimPy package: 
1.	Environment (simpy.Environment): Execution environment that passes simulation time by stepping from event to event. We think of the environment as the “clock” and the “process queue.”
2.	Events (simpy.events):
a.	simpy.events.Timeout - Event that gets triggered after a delay has passed. Used throughout our simulation to manipulate “simulation time” for all processes (for example, the shift_manager process uses timeout to change work shifts every 8 hours).
b.	simpy.events.Process - Process an event yielding generator. Used in our simulation to yield a variety of custom process generators including shift_manager, worker_shift, picker, stower, packer, order_age_monitor, order_receiver, inbound_receiving_dock, holding_cost_monitor, print_kpis, and write logs. 
3.	Shared Resources (simpy.resources):
a.	simpy.resources.Container - Resource for sharing homogeneous matter between processes. Used in our simulation to track product inventory in our custom InventoryBin objects that are initialized to manage inbound parking, inventory storage, and inventory holding levels.
b.	simpy.resources.Store - Resource for sharing arbitrary objects between processes. Used in our sim to handle received customer orders and packing station queues. 
c.	simpy.resources.resource.Resource - Resource with capacity of usages slots that can be requested by processes. Used in our simulation for assigning packers to packing stations (each packing station has only one usage slot).

Our final simulation model follows a straight forward flow: First, the user sets variables to configure fulfillment center operation policies, Next components are created and added to the environment to set up the simulation. Finally the simulation runs and logs results.

## In Summary
The simulation of the entire fulfillment center has shown us how different functions operate together, and that changes in one function can affect others. In the inbound operation, we found that the daily delivery schedule can ultimately offset its higher delivery cost with savings in inventory holding costs. To further save on costs, we decided to implement the random inventory storage as pickers are more efficient under this policy. Finally, we minimized the packing stations enough for packers to effectively handle the orders without excess labor cost. As a unified operation, the simulation, simplified by SimPy, flows seamlessly from the inbound receiving operations, to storage, and the packing operations.
