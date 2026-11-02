| Policy class | n (MtQ) | Reference pattern | Mind the Query pattern | Status |
|---|---:|---|---|---|
| C0_column_name_control | 5 | accept CB/GQ/TG/PIPE/CL/CS; reject CT | accept CB/GQ/TG/CL/CS; reject CT/PIPE | PARTIAL_REPLICATION |
| R1_numeric_type | 10 | accept CB/GQ/TG/CS; reject CT/PIPE/CL | accept CB/GQ/TG/CS; reject CT/PIPE; CL:MIXED | PARTIAL_REPLICATION |
| R2_float_tolerance | 10 | accept TG/CL; reject CT/CB/GQ/PIPE/CS | accept TG; reject CT/CB/GQ/PIPE/CS; CL:MIXED | PARTIAL_REPLICATION |
| R3_row_order | 10 | accept CT/CB/GQ/PIPE/CL/CS; reject TG | accept CT/CB/GQ/PIPE/CL/CS; reject TG | EXACT_REPLICATION |
| R4_duplicates | 10 | accept PIPE/CS; reject CT/CB/GQ/TG/CL | accept PIPE/CS; reject CT/CB/GQ/TG/CL | EXACT_REPLICATION |
| R5_column_order | 10 | S1: accept CT/CB/GQ/PIPE/CL; reject TG/CS | accept CT/CB/GQ/PIPE/CL; reject TG/CS | NEW_EVIDENCE (S1: CONSISTENT_WITH_S1) |
| R6_reference_order | 10 | S1: accept CT/TG/PIPE/CL/CS; reject CB/GQ | accept CT/TG/PIPE/CL/CS; reject CB/GQ | NEW_EVIDENCE (S1: CONSISTENT_WITH_S1) |
| R7_list_order | 10 | S1: accept CB; reject CT/GQ/TG/PIPE/CL; CS:ERROR | accept CB; reject CT/GQ/TG/PIPE/CL; CS:ERROR | NEW_EVIDENCE (S1: CONSISTENT_WITH_S1) |
| R8_null_natural | 2 | accept all except GQ rejects numeric-NULL cases | accept CT/CB/TG/PIPE/CL/CS; reject GQ | NOT_TESTABLE |

Study decision by the frozen rule: **A_STRONG_CROSS_BENCHMARK_REPLICATION**
