/* SAMPLE DATA ONLY: made-up companies and numbers so the page can be designed and tested.
   To go live, replace window.dxLoad with a function that fetches real rows from the server in the same shape. */
(function(){
// name, ticker, sector, cap, price, annual dividend per share, years paid in a row, payout %, frequency, 5y dividend growth %, ex-date in N days
const T=[
['Northvale Bank','NVBK','Banking','Large',1480,26,22,24,'Annual',14,12],['Kaveri Finance','KVFN','Finance','Large',910,18,15,31,'Half-yearly',11,31],['Meghdoot Bank','MGDB','Banking','Mid',262,9.5,9,22,'Annual',17,44],
['Sahyadri Infotech','SHIT','IT','Large',1710,66,18,52,'Quarterly',12,6],['Tarang Digital','TRDG','IT','Large',3480,112,20,58,'Quarterly',13,19],['Orbit Systems','ORBS','IT','Mid',845,40,11,47,'Half-yearly',9,52],['Cresta Software','CRSW','IT','Small',390,11,6,35,'Annual',21,63],
['Gangotri Consumer','GNCO','FMCG','Large',2490,48,25,66,'Half-yearly',8,23],['Haldi Foods','HLDF','FMCG','Mid',640,14,12,41,'Annual',10,37],['Lotus Home Care','LTHC','FMCG','Large',2210,43,17,72,'Half-yearly',7,9],
['Aarav Steel Works','ARST','Metals & Mining','Large',165,21,14,38,'Quarterly',26,4],['Bharat Coalfields','BHCF','Metals & Mining','Large',405,28.5,19,62,'Quarterly',16,14],['Zinc Valley Ltd','ZNVL','Metals & Mining','Large',520,48,13,85,'Half-yearly',19,27],['Deccan Alloys','DCAL','Metals & Mining','Small',96,5.5,5,29,'Annual',33,70],
['Surya Oil Refining','SYOR','Energy','Large',275,22,16,44,'Annual',12,17],['Petra Gas Utilities','PTGU','Energy','Mid',480,19,10,54,'Half-yearly',9,41],['Vayu Wind Energy','VYWE','Energy','Small',58,2.4,4,26,'Annual',22,66],
['Ganga Power Grid','GNPG','Power','Large',302,12.8,13,68,'Quarterly',6,8],['Rudra Thermal','RDTH','Power','Large',358,10.5,8,39,'Annual',15,35],['Tapti Hydro','TPHY','Power','Mid',74,3.1,7,48,'Annual',5,58],
['Ayur Pharma','AYPH','Pharma','Large',1925,64,21,43,'Half-yearly',11,21],['Sanjeevani Labs','SNLB','Pharma','Mid',3120,95,16,50,'Annual',8,33],['Vita Remedies','VTRM','Pharma','Small',212,6,6,32,'Annual',18,57],
['Rathod Motors','RTMT','Auto','Large',12340,140,12,36,'Annual',20,29],['Chakra Auto Parts','CKAP','Auto','Mid',940,23,9,34,'Half-yearly',13,46],['Vahan Tyres','VHTY','Auto','Mid',1350,32,14,40,'Annual',10,15],
['Himgiri Cement','HMGC','Cement','Large',11280,240,11,70,'Annual',17,38],['Sagar Cement Works','SGCW','Cement','Mid',365,9,8,33,'Annual',12,49],['Narmada Build Mat','NRBM','Cement','Small',148,4.2,5,28,'Annual',25,68],
['Indus Capital','INCP','Finance','Mid',545,16,10,37,'Half-yearly',14,25],['Rajat Housing Finance','RJHF','Finance','Mid',420,13,9,30,'Annual',16,54],['Sunrise Insurance','SNIN','Finance','Large',630,7.5,7,26,'Annual',9,61],
['Kisan Fertilisers','KSFR','Chemicals','Mid',152,12.4,18,57,'Half-yearly',8,18],['Neel Specialty Chem','NLSC','Chemicals','Small',730,22,7,31,'Annual',23,40],['Pragati Paints','PRPT','Chemicals','Large',2780,41,15,55,'Quarterly',9,11],
['Jalaram Logistics','JLLG','Industrials','Mid',390,10,6,33,'Annual',15,60],['Mahaveer Engineering','MHEN','Industrials','Small',1180,28,8,29,'Half-yearly',19,47],['Trident Rail Systems','TRRS','Industrials','Mid',275,6.8,5,42,'Annual',12,72]];
const MAXD=75;
window.DX_SECTORS=[...new Set(T.map(t=>t[2]))].sort();
window.dxLoad=function(){const d0=new Date();d0.setHours(0,0,0,0);
 return Promise.resolve(T.map(t=>{const ex=new Date(d0.getTime()+t[10]*864e5);
  return{name:t[0],sym:t[1],sector:t[2],cap:t[3],price:t[4],dps:t[5],yield:Math.round(t[5]/t[4]*10000)/100,years:t[6],payout:t[7],freq:t[8],cagr:t[9],exIn:t[10],ex:ex}}))};
})();
