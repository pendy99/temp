Optimization for Long Fat Network Servers
1. Install tsunami version of BBR
   ```shell
   wget https://raw.githubusercontent.com/KozakaiAya/TCP_BBR/master/script/dkms_install.sh
   ```
   Select the kernel version and tsunami.

2. Add the following content to the middle or end of `/etc/security/limits.conf` to increase the maximum number of open files in the Linux system:
   ```
   * soft nproc 11000
   * hard nproc 11000
   * soft nofile 655350
   * hard nofile 655350

   root soft nproc 11000
   root hard nproc 11000
   root soft nofile 655350
   root hard nofile 655350
   ```

3. Modify `/etc/sysctl.conf` and add the following content:
   ```
   net.ipv4.tcp_slow_start_after_idle = 0
   net.ipv4.route.flush = 1
   net.ipv4.tcp_no_metrics_save = 1
   net.ipv4.tcp_moderate_rcvbuf = 1
   net.ipv4.tcp_window_scaling = 1
   net.ipv4.tcp_adv_win_scale = 3
   ```

4. Increase network card Ring buffer
   First, check the maximum size allowed for the network card:
   ```shell
   ethtool -g <network_card_name>
   ```
   Then modify the settings:
   ```shell
   ethtool -G <network_card_name> rx 2048  # Use the maximum or half of the maximum
   ethtool -G <network_card_name> tx 2048  # Use the maximum or half of the maximum
   ```

5. Use the script to calculate the suitable kernel parameters and add them to the end of `/etc/sysctl.conf`:
   ```shell
   wget https://github.com/pendy99/temp/raw/main/test_bdp.py
   python3 test_bdp.py
   ```
   Append the content after the line "please append the following lines to /etc/sysctl.conf" to the end of `/etc/sysctl.conf`. Note that if the calculated values are lower than the current system values, please keep the current default values.

6. Adjust the initial send and receive window sizes to increase transmission speed.
   First, use the command `ip route` to view your routing table. For example:
   ```
   default via 114.237.54.121 dev enp129s0 proto static
   114.237.54.120/29 dev enp129s0 proto kernel scope link src 114.237.54.122
   ```
   Then, use the `ip route change` command to modify the initial window size (Linux default is 10 times). For example, change it to 30 times:
   ```shell
   ip route change default via 114.237.54.121 dev enp129s0 proto static initrwnd 30 initcwnd 30
   ```
   This command modifies the first line of the output from the `ip route` command. Add `ip route change` at the beginning, and add `initrwnd 30 initcwnd 30` at the end. You can try different values to find an appropriate multiplier. Typically, CDNs use 30 or 60 times.
