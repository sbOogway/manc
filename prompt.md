# manc - macro analysis, news and calendar

## description

your job is to build an agentic system to gather market and global macroeconomics news from trusted sources and build a report and index score out of hundred for selected assetss, such as forex pairs, commodities, cryptos, stock, metals and so on.

## architecture of the system

### operations

every day, the system should look at the next month economic calendar, recognize the key events in it and look at recent news.

once we gathered all the relevant information, we proceed to create an index score. it should be a number that goes from 0 to 100. i need help to define the formula to calculate the index.

once we calculated the value, we should store it somewhere (need to define this as well) and be able to plot a graph with the daily forecasts.

### data

as data provider we should use the openbb. it has basically all the infos we need. need to check further. https://github.com/OpenBB-finance/OpenBB.
for news we should use rss feeds. for sources i would like to use reuters and some others, that we further need to research.

### code

the project should be written in python using uv as package manager. each module should have an interface that is used to communicate with other modules.

every module should have its test suite using pytest.

we need to display the data in a web page of some sort.

before proceding generate me an artifact with the the blueprint to build the project. also set up a github repo and create proper milestones. when u will implement features i need u to use github issues. please dont make the system more complicated that it needs to be
