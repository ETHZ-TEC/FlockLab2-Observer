#!/bin/bash

# logs the output of chronyc sourcestats of the given source

LOGFILE="log/chronystats.log"
DURATION=3600        # in seconds
INTERVAL=10          # in seconds
TIMESOURCE="PTP"

COUNT=$(echo "$DURATION / $INTERVAL" | bc)

while [ $COUNT -gt 0 ]
do
  RES=$(chronyc sourcestats | tail -n1)
  if [ $? -eq 0 ] && [[ $RES == *"$TIMESOURCE"* ]]; then
    TIMESTAMP=$(date +%s)
    #echo "$TIMESTAMP,$RES"
    CONV=$(echo $RES | awk '{printf "%s,%s,%s,%s,%s,%s,%s\n",$2,$3,$4,$5,$6,$7,$8}')
    echo "$TIMESTAMP,$CONV" >> $LOGFILE
  fi
  ((COUNT--))
  sleep $INTERVAL
done
