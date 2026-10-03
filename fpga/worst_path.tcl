project_open de10_cpu -revision de10_cpu
create_timing_netlist
read_sdc
update_timing_netlist
report_timing -setup -npaths 4 -detail summary -file worst_path.txt
project_close
