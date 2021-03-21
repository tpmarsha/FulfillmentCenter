# Amazon Fullfilment Center Operations Simulation

## Introduction

Our team developed an optimized operations and supply chain management policy for a fulfillment center. After data analysis, we created a systems-level simulation to test different strategies for the center’s operations. Although complex, the comprehensive approach allows us to evaluate how the sub-operations within the center interact with each other. This readme covers our simulation architecture, initial exploratory analysis of the 52-week orders,and the following specific operations: 1) Inbound Receiving, 2) Storage, and 3) Outbound Processing.

## Orders and Capacity Exploration
*Demand Patterns*

Based on the 52-week orders data, we have uncovered the demand patterns for each item type. Understanding the demand patterns enables us to predict new orders and plan schedules for workers and the optimal shipment quantity. To generate new orders for testing, we explored the distribution of orders by different timeframes (i.e. month, week, day, hour) and item type. As shown in the figure below left, there are more orders on the weekends displayed in red (Friday to Sunday) with a small peak in the middle of the week. The line graphs display order quantities for each item; t-shirts are the most popular item by quantity ordered while sneakers are the least popular item. Interestingly, hoodies and sweatpants follow the same distribution - they seemingly complement each other in an outfit very well!

