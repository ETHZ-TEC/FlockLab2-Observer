#!/bin/bash
# this script can be used to run a test directly on the observer (no interaction with the server)

TESTID=1
SETUPTIME=25
TESTTIME=15
TEMPLATE=$(cat <<- END
<?xml version="1.0" encoding="UTF-8"?>
<obsConf>
<obsTargetConf>
	<voltage>3.3</voltage>
	<image core="0">TESTIMAGE</image>
	<slotnr>1</slotnr>
	<platform>dpp2lora</platform>
</obsTargetConf>
<obsSerialConf>
	<baudrate>115200</baudrate>
	<cpuSpeed>80000000</cpuSpeed>
</obsSerialConf>
<obsDebugConf>
	<cpuSpeed>80000000</cpuSpeed>
	<prescaler>16</prescaler>
	<loopDelay>11</loopDelay>
	<dataTraceConf>
		<variable>0x20000020</variable>
		<varName>counter</varName>
		<mode>W</mode>
		<size>4</size>
	</dataTraceConf>
</obsDebugConf>
<obsGpioMonitorConf>
	<pins>LED1 INT1</pins>
</obsGpioMonitorConf>
<obsGpioSettingConf>
	<pinConf>
		<pin>RST</pin>
		<level>high</level>
		<timestamp>STARTTIME</timestamp>
	</pinConf>
	<pinConf>
		<pin>RST</pin>
		<level>low</level>
		<timestamp>STOPTIME</timestamp>
	</pinConf>
</obsGpioSettingConf>
</obsConf>
END
)

if [ $# -lt 1 ]
then
  echo "usage: $0 [image filename]"
  exit 1
fi
TESTIMAGE=$1

CURDIR=$(pwd)
if [[ $TESTIMAGE != *"${CURDIR}"* ]]
then
  TESTIMAGE=${CURDIR}/${TESTIMAGE}
fi

if [ ! -e $TESTIMAGE ]
then
  echo "file $TESTIMAGE not found"
  exit 1
fi

# remove results directory
RESULTSDIR=/home/flocklab/data/results/${TESTID}
rm -rf $RESULTSDIR

# set start time
STARTTIME=$(echo "$(date +%s) + ${SETUPTIME}" | bc)
STOPTIME=$(echo "${STARTTIME} + ${TESTTIME}" | bc)

XMLCONFIG=${CURDIR}/config.xml
echo "${TEMPLATE}" > $XMLCONFIG
sed -i "s#TESTIMAGE#${TESTIMAGE}#" $XMLCONFIG
sed -i "s/STARTTIME/${STARTTIME}/" $XMLCONFIG
sed -i "s/STOPTIME/${STOPTIME}/" $XMLCONFIG

echo "configuring..."

/home/flocklab/observer/testmanagement/flocklab_starttest.py --testid=${TESTID} --xml=${XMLCONFIG}

CURTIME=$(date +%s)
TIMELEFT=$(echo "${STARTTIME} - ${CURTIME}" | bc)

echo "test will start in ${TIMELEFT}s"
sleep $TIMELEFT
echo "test started"
echo "waiting for test to finish "

while [ $CURTIME -lt $STOPTIME ]
do
  echo -n "."
  sleep 1
  CURTIME=$(date +%s)
done

echo ""
echo "cleaning up..."

/home/flocklab/observer/testmanagement/flocklab_stoptest.py --testid=${TESTID} --xml=${XMLCONFIG}

echo "test finished!"

