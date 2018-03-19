import logging
import threading

from main import upload_batch, get_filenames, startdir, XlsIterator, upload_df, show_1265_warnings
from db import open_db, close_db
from queue import Queue


def upload_worker(queue: Queue):
    cur, conn = open_db()
    print('Worker started, waiting for data...')
    SQL, batch = queue.get()
    fname = batch[0]['bkf_filename'] if batch else None
    print(f'WORKER: Uploading {fname} to DB....')
    while batch:
        old_fname = fname
        fname = batch[0]['bkf_filename']
        if fname != old_fname:
            print(f'WORKER: Uploading {fname} to DB....')
        warnings_ = upload_batch(SQL, batch, cur, conn)
        SQL, batch = queue.get()
        show_1265_warnings(warnings_)
    close_db(cur, conn)


if __name__ == "__main__":
    import time
    t1 = time.time()
    print('Getting filenames...')
    filenames = get_filenames(startdir)
    print('Initializing parser')
    walkall = XlsIterator(filenames, 0)

    # Создаем очередь для батчей загрузки в бд, ее будет разбирать отдельный тред
    batch_queue = Queue()
    upload_thread = threading.Thread(target=upload_worker, args=(batch_queue,))
    upload_thread.daemon = True
    print('Start upload to db thread...')
    upload_thread.start()

    for df in walkall:
        upload_df(df, batch_queue)

    print('Кладем пустой batch')
    batch_queue.put(('', []))
    upload_thread.join()
    t2 = time.time()
    print('Время выполнения', t2-t1)
