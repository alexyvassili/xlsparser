import logging
import os
import pandas as pd
from config import startdir, BLACKLIST, bkf_table
from xlsparser import GpXlsConfig, GpXlsParser
from db import open_db, close_db

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class XlsIterator:
    def __init__(self, filenames, start=0):
        self.current = start
        self.filenames = filenames
        self.end = len(filenames)
        self.config = GpXlsConfig()

    def __iter__(self):
        return self

    def __next__(self):
        if self.current >= self.end:
            raise StopIteration

        logging.warning(f"Reading file {self.current+1} of {self.end}")
        parser = GpXlsParser(self.filenames[self.current], self.config)
        df = parser.parse()
        self.current += 1
        return df


def not_in_blacklist(path):
    for item in BLACKLIST:
        if item in path:
            return False
    return True


def get_filenames(startdir):
    filenames = []
    for directory, subdirectories, files in os.walk(startdir):
        filenames += [os.path.join(directory, file) for file in files if 'xls' in file.lower()]
    filenames = list(filter(not_in_blacklist, filenames))
    return filenames

def upload_df(df: pd.DataFrame):
    fields = ', '.join(df.columns)
    values_fields = [f'%({field})s' for field in df.columns]
    values_fields = ', '.join(values_fields)
    SQL = f"""INSERT INTO {bkf_table} ({fields}) \n
                VALUES ({values_fields})"""
    # дальше надо писать VALUES %s %s и т д скорее всего это зависит от типа так что надо смотреть и потом передавать кортежи
    # вот так: sql = "INSERT INTO TABLE_A(COL_A,COL_B) VALUES(%s, %s)"
    # a_cursor.execute(sql, (val1, val2))
    print(SQL)
    # чтобы cursor.execute() это ел, нужно NaN заменить на None
    df = df.where(df.notnull(), None)
    cur, conn = open_db()
    for index, row in df.iterrows():
        cur.execute(SQL, row.to_dict())
    conn.commit()
    close_db(cur, conn)

if __name__ == "__main__":
    filenames = get_filenames(startdir)
    walkall = XlsIterator(filenames, 9)
    df = next(walkall)
    upload_df(df)
