#!/usr/bin/env bash
#
# Description: IO test script, modified from bench.sh
# https://github.com/teddysun/across/blob/master/bench.sh
#
# Thanks: LookBack <admin@dwhd.org>, Teddysun <i@teddysun.com>
#

io_test() {
  (LANG=C dd if=/dev/zero of=benchtest_$$ bs=512k count=$1 conv=fdatasync && rm -f benchtest_$$) 2>&1 | awk -F, '{io=$NF} END { print io}' | sed 's/^[ \t]*//;s/[ \t]*$//'
}

perform_io_test() {
  freespace=$(df -m . | awk 'NR==2 {print $4}')
  if [ -z "${freespace}" ]; then
    freespace=$(df -m . | awk 'NR==3 {print $3}')
  fi
  if [ ${freespace} -gt 1024 ]; then
    INFO "💽 Free Space: ${YELLOW}${freespace}MB${NOFORMAT}"
    INFO "📈 Performing I/O Speed test..."

    writemb=2048 # 2048 512K blocks = 1G
    io1=$(io_test ${writemb})
    INFO "💽 I/O Speed(1st run) : ${YELLOW}$io1${NOFORMAT}"
    io2=$(io_test ${writemb})
    INFO "💽 I/O Speed(2nd run) : ${YELLOW}$io2${NOFORMAT}"
    io3=$(io_test ${writemb})
    INFO "💽 I/O Speed(3rd run) : ${YELLOW}$io3${NOFORMAT}"
    ioraw1=$(echo $io1 | awk 'NR==1 {print $1}')
    [ "$(echo $io1 | awk 'NR==1 {print $2}')" == "GB/s" ] && ioraw1=$(awk 'BEGIN{print '$ioraw1' * 1024}')
    ioraw2=$(echo $io2 | awk 'NR==1 {print $1}')
    [ "$(echo $io2 | awk 'NR==1 {print $2}')" == "GB/s" ] && ioraw2=$(awk 'BEGIN{print '$ioraw2' * 1024}')
    ioraw3=$(echo $io3 | awk 'NR==1 {print $1}')
    [ "$(echo $io3 | awk 'NR==1 {print $2}')" == "GB/s" ] && ioraw3=$(awk 'BEGIN{print '$ioraw3' * 1024}')
    ioall=$(awk 'BEGIN{print '$ioraw1' + '$ioraw2' + '$ioraw3'}')
    ioavg=$(awk 'BEGIN{printf "%.1f", '$ioall' / 3}')
    INFO "📊 I/O Speed(average) : ${YELLOW}$ioavg MB/s${NOFORMAT}"

    # Convert ioavg to integer
    ioavg=$(echo $ioavg | awk -F. '{print $1}')

    if [[ "$ioavg" -lt 300 ]]; then
      WARN "🚨 I/O Speed is too slow!"

      # Continue if user confirm, timeout in 10 seconds
      local answer
      read -r -t 10 -p "Continue? [y/N] " answer

      if [[ "$answer" =~ ^([yY][eE][sS]|[yY])+$ ]]; then
        INFO "🚀 Continue..."
      else
        ERROR "🚫 I/O Speed is too slow, exit!"
        exit 1
      fi
    fi

    INFO "🎉 I/O Speed test completed!"
  else
    ERROR "🚫 Not enough space for I/O Speed test!"
  fi
}
