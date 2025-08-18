#!/usr/bin/env python3

import psycopg2

IDLE_TIMEOUT_MINUTES = 10

def main():
    with psycopg2.connect(dbname="postgres") as conn, conn.cursor() as cur:
        sql_query = f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE
            state = 'idle'
            AND NOW() - state_change > INTERVAL '{IDLE_TIMEOUT_MINUTES} minutes'
            AND pid <> pg_backend_pid();
        """
        cur.execute(sql_query)
        num_terminated = len(cur.fetchall())
    if num_terminated > 0:
        print(f"terminated {num_terminated} connections")

if __name__ == "__main__":
    main()
