Python IOC <==> aioca/p4p Performance Tests
===========================================

Packages used:

- aioca             1.4
- epicscorelibs     7.0.6.99.2.0
- epicsdbbuilder    1.5
- p4p               4.1.1
- psutil            5.9.1
- pvxslibs          0.3.1
- softioc           4.1.0


Performance (Python IOC / aioca)
********************************

- IOC on p45-control
- Client on p45-ws001
- Monitoring network for 20s and averaging
- CPU monitored with top


=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========
Server                                           Client
-----------------------------------------------  --------------------------------------------------
N PVs  Rate(Hz)  CPU(%)  Sent(kB/s)  Recv(kB/s)  N PVs   N Monitors  CPU(%)  Sent(kB/s)  Recv(kB/s)
=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========
0      0         0       6           6           0       0           0       1           0
1      100       6       520         3           1       1000        120     2           528
1      10        1       245         5           1       1000        61      3           245
1000   10        126     915         340         1000    1           71      330         915
500    10        60      460         335         500     1           45      335         460
100    100       90      257         12          1       100         58      23          280
100    100       95      516         12          100     10          120     3           506
100    100       105     520         10          100     50          120     3           512
100    100       cbLow ring buffer full          100     70          
-----  --------  ------------------------------  ------  ----------  ------  ----------  ----------
=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========


Attempts to increase the number of PVs above 100 with 100Hz update rate resulted in failures of the
Python IOC (with no monitors).  Data rates did not appear to be altered by increasing the number of 
monitors on individual PVs (perhaps to be expected if the client is intelligent)



Performance (Python IOC / p4p)
******************************

- IOC on p45-control
- Client on p45-ws001
- Monitoring network for 20s and averaging
- CPU monitored with top


=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========
Server                                           Client
-----------------------------------------------  --------------------------------------------------
N PVs  Rate(Hz)  CPU(%)  Sent(kB/s)  Recv(kB/s)  N PVs   N Monitors  CPU(%)  Sent(kB/s)  Recv(kB/s)
=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========
0      0         0       6           6           0       0           0       1           0
1      100       25      1150        5           1       1000        120     5           1150
1      10        22      540         7           1       1000        63      4           540
1000   10        159     1050        325         1000    1           60      325         1050
500    10        75      600         310         500     1           50      310         600
100    100       112     552         16          1       100         62      8           541
100    100       125     1155        15          100     10          129     6           1127
100    100       125     1215        15          100     50          132     5           1160
100    100       132     1215        14          100     70          132     5           1175
100    100       135     1200        15          100     100         135     4           1155
100    100       200     1200        15          100     1000        132     4           1155
-----  --------  ------------------------------  ------  ----------  ------  ----------  ----------
=====  ========  ======  ==========  ==========  ======  ==========  ======  ==========  ==========


Results here also suggested that increasing the numer of monitors on the same PV did not alter the rate
of data.  I do not understand why increasing the number of monitors by a factor of 10 increased significantly 
the load on the server, as the data rate suggests the monitors did not result in additional traffic.


Conclusion
**********

The Python IOC appears to be close to its limit with 100 records at 100Hz even without any clients connecting.
There was a fair bit of instability, quite often ring buffer error messages occured when the client applications
were started or stopped.
These tests also do not verify that the 100Hz updates were received without loss by the clients as no verification
was made by the clients on the quantity or values received.
