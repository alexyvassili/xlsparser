import logging
import warnings
import os
import pandas as pd
from config import startdir, BLACKLIST, bkf_table
from xlsparser import GpXlsConfig, GpXlsParser
from progressbar import printProgressBar
import MySQLdb
from db import open_db, close_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

warnings.filterwarnings('error', category=MySQLdb.Warning)


class XlsIterator:
    """Итератор, проходит по списку xls файлов и парсит их по очереди.
    Никакой проверки входных данных не делается!"""
    def __init__(self, filenames, start=0):
        print('Initializing...')
        self.current = start
        self.filenames = filenames
        self.end = len(filenames)
        self.config = GpXlsConfig()

    def __iter__(self):
        return self

    def __next__(self):
        if self.current >= self.end:
            raise StopIteration

        print()
        print(f"Reading file {self.current+1} of {self.end}")
        parser = GpXlsParser(self.filenames[self.current], self.config)
        df = parser.parse().process()
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


def split_df(df, batch_size):
    """Разделяет датафрейм на списки словарей заданного размера"""
    batches = []
    batch = []
    for index, row in df.iterrows():
        batch.append(row.to_dict())
        if index % batch_size == 0:
            batches.append(batch.copy())
            batch.clear()
    if batch:
        batches.append(batch)
    return batches


def get_address_from_mysql_warning(warning: Warning):
    text = warning.args[1].split("'")
    field = text[1]
    row_num = text[2].split()[-1]
    return int(row_num), field


def upload_batch(SQL, batch, cur, conn):
    warnings_ = []
    try:
        cur.executemany(SQL, batch)
    except MySQLdb.Warning as e:
        if 'Data truncated for column' in e.args[1]:
            row_num, field = get_address_from_mysql_warning(e)
            value = batch[row_num][field]
            warnings_.append(
                {
                    'row_num': row_num,
                    'file_row_num': batch[row_num]['bkf_row_num'],
                    'field': field,
                    'value': value,
                    'type': type(value),
                    'length': len(value) if type(value) == str else None,
                }
            )
        else:
            print()
            print('*' * 100)
            print('Unexpected MySQL Warning:', e)
            print('*' * 100)
            print()
    conn.commit()
    return warnings_


def show_1265_warnings(warnings_):
    if warnings_:
        logging.warning('DURING UPLOAD SOME (1265, "Data truncated for column N at row M") WARNINGS WAS CATCHED: ')
        print()
        print('*' * 100)
        for w in warnings_:
            print(w)
        print('*' * 100)
        print()


def upload_df_with_batches(SQL, df, queue=None, batch_size=500):
    # чтобы cursor.execute() это ел, нужно NaN заменить на None
    df = df.where(df.notnull(), None)
    batches = split_df(df, batch_size)
    length = len(batches)
    logging.info(f'ALL ITEMS: {sum([len(batch) for batch in batches])} IN {length} BATCHES')
    logging.info(f'DF SHAPE: {df.shape}')
    warnings_ = []
    if not queue:
        cur, conn = open_db()
        logging.info(f"Uploading items")
        progress_string = 'Uploading dataframe to DB: '
        printProgressBar(0, length, prefix=progress_string, suffix='Complete', length=100)
        for i, batch in enumerate(batches):
            warnings_ = upload_batch(SQL, batch, cur, conn)
            printProgressBar(i+1, length, prefix=progress_string, suffix='Complete', length=100)
        conn.commit()
        close_db(cur, conn)
    else:
        print('Putting {} to Queue...'.format(batches[0][0]['bkf_filename']))
        for batch in batches:
            queue.put((SQL, batch))
    show_1265_warnings(warnings_)


def upload_df(df: pd.DataFrame, queue=None):
    fields = ', '.join(df.columns)
    values_fields = [f'%({field})s' for field in df.columns]
    values_fields = ', '.join(values_fields)
    SQL = f"""INSERT INTO {bkf_table} ({fields}) \n
                VALUES ({values_fields})"""
    upload_df_with_batches(SQL, df, queue)


def main():
    filenames = get_filenames(startdir)
    # file = [i for i in filenames if 'Казань' in i][0]
    # index = filenames.index(file)
    walkall = XlsIterator(filenames, 0)
    for df in walkall:
        upload_df(df)


if __name__ == "__main__":
    import time
    t1 = time.time()
    main()
    t2 = time.time()
    print('Время выполнения', t2 - t1)
