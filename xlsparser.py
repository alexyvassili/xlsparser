import numpy as np
import pandas as pd
from pandas.errors import ParserError
import os
import logging
from config import GpXlsConfig


class GpXlsParser:
    def __init__(self, file: str, config: GpXlsConfig):
        # приходится хранить у себя объект конфига, так как иногда нужно подменить
        # конфигурацию полей "на лету", поэтому свойства полей реализованы
        # через @property
        self.config_obj = config
        self.file = file  # full path
        self.filename = os.path.basename(file)
        self.skip = 0
        # для записи номера строки в исходном файле нужна разность между номером строки в xls
        # и индексом в датафрейме, 2 по умолчанию, так как нумерация в xls с 1,
        # в пандас - с 0, плюс одна строка - шапка
        self.delta = 2
        self.df = None
        self.config = config.get_config(self.file)
        self.branch_name = self.config['branch_name']
        self.multirow = 0

    @property
    def key_field(self):
        """ключевое поле - инвентарный номер, он всегда есть, по нему делаем фильтр"""
        return self.config['key_field']

    @property
    def name_field(self):
        """ поле названия - по нему делаем фильтр если в инв. номере есть мусор"""
        return self.config['name_field']

    @property
    def fields(self):
        return self.config['fields']

    @property
    def mapper(self):
        return self.config['mapper']

    def _findheader(self):
        """находим заголовок (строка, содержащая поле с инвентарным номером) и считываем его
        проблема: если документ начинается с нескольких пустых строк, то парсер xls считает их за одну,
        соответственно, индекс найденного заголовка не будет совпадать с реальным
        поэтому, вызываем функцию, смещаясь вниз, пока не получим нужное поле в заголовке датафрейма"""
        print(f'Reading {self.file}...')
        df = pd.read_excel(self.file, skiprows=self.skip, dtype=str)
        logging.debug(f'COLS IN DF: {df.columns}')
        # пропускаем шапку таблицы
        if self.key_field in df.columns:
            return df
        else:
            ix = 0
            logging.info('SEARCHING HEADER')
            for index, row in df.iterrows():
                # ищем строчку с ключевым полем
                # и считаем её шапкой таблицы
                header = list(row)
                logging.debug(f'{ix}, {header}')
                if (self.key_field in header) or (self.key_field == index):
                    logging.debug(f'CATCH {index} {header}')
                    logging.debug(f'INDEX {ix+1} {ix == index}')
                    self.skip += ix + 1
                    break
                ix += 1
            logging.info('Re-reading...')
            df = self._findheader()
            return df

    def _find_multirow_header(self):
        """вычисляем количество строк в шапке, для этого смотрим
        сколько в столбце ключевого поля значений NaN
        поэтому ключевое поле:
        - должно быть во всех таблицах
        - должно занимать всегда одну строку
        - должно быть всегда заполнено.
        В одной таблице после шапки есть пустая строка, наш парсер считает её частью шапки,
        и от этого pandas.read_excel падает с ошибкой. Поэтому если не удалось распарсить
        файл с multirow = n, то пробуем это сделать с multirow = n-1
        """
        logging.debug('MULTIROW')
        logging.debug('FIRST 5 IN KEY FIELD')
        logging.debug(f"\n{self.df[self.key_field][:5]}")
        logging.debug(f"\n{self.df[self.key_field][:5]} == 'nan'")
        count = 0
        for i in self.df[self.key_field] == 'nan':
            if not i: break
            count += 1
        logging.info(f'MULTIROW COUNT: {count}')
        if count:
            logging.debug('MULTIROW found')
        return count

    def _rewrite_index(self):
        """если шапка состоит из нескольких строк, переделываем индекс таблицы вручную.
        генерируем свой индекс, затем парсим заново без индекса, приделывая свой.
        """
        if self.multirow < 1:
            raise ValueError('Unexpected value of multirow while cutting header')
        header = [i for i in range(self.multirow + 1)]
        logging.debug(f'HEADER: {header}')
        try:
            df = pd.read_excel(self.file, skiprows=self.skip, header=header, dtype=str)
        except ParserError:
            logging.debug('ERROR, trying cut header')
            self.multirow -= 1
            return self._rewrite_index()
        new_index = []
        for i in df.columns:
            new_index.append('\n'.join([j for j in i if 'Unnamed' not in j]))
        # pandas в режиме multirow header принудительно создает из первой колонки индекс, поправляем
        new_index = [df.columns.names[0], ] + new_index
        logging.debug('CREATING NEW INDEX')
        logging.debug(new_index)
        self.skip += len(header)
        # корректируем смещение, так как пропускаем исходную шапку
        self.delta -= 1
        # заново парсим файл, уже без шапки, припиливаем к нему свою сгенерированную ранее
        df = pd.read_excel(self.file, skiprows=self.skip, index_col=None, header=None, dtype=str, names=new_index)
        return df

    def _mapped(self):
        """
        для логирования: пишем поля, которые не смапились
        (есть в настройках, но не найдены в реальном файле)
        если не все ожидаемые поля найдены в файле, ничего не делаем,
        хотя можно бы бросить исключение(и сейчас оно бросается).
        """
        unmapped = set(self.fields) - set(self.df.columns)
        logging.debug(f'FIELDS: {set(self.fields)}')
        if unmapped:
            # если не получилось смапить все поля, возможно в настройках есть второй столбец
            # с тем же именем филиала и суффиксом  '//add', пробуем подменить config на него
            logging.info(f'UNMAPPED: {unmapped}')
            logging.info('TRYING VARIABLE FIELDS')
            try:
                self.config = self.config_obj.get_alter_config(self.file)
            except KeyError:
                logging.info('NO VARIABLE FIELDS')
                raise ValueError(f'Mapping Error: Unmapped fields: {unmapped}')
            else:
                self._mapped()
        else:
            logging.info('ALL FIELDS MAPPED')

    def _check_first_string(self):
        # под шапкой бывает нумерация столбцов
        # идем снизу и ищем строку где все значения содержат только цифры.
        # удаляем ее и все строки выше
        # начинаем с пятой строки, просто потому что файлов с бОльшим количеством
        # служебных строк нет
        for row in range(5, -1, -1):
            if all([i.isdigit() for i in self.df.loc[row] if type(i) == str]):
                logging.info(f'Skipping first {row+1} strings...')
                self.df = self.df.drop([j for j in range(row + 1)])
                break

    def _clear_df(self):
        """смотрим в каком столбце больше нанов и по нему делаем drop
         это либо инвентарный номер, либо наименование, потому что то там, то там
         попадаются слова типа Итого, в зависимости от файла.
         на данный момент потери всего три элемента (в одной таблице фильтруем по имени,
         а там у трех элементов нет имени)"""
        key_drop_rows_count = self.df[self.df[self.key_field] == 'nan'].shape[0]
        name_drop_rows_count = self.df[self.df[self.name_field] == 'nan'].shape[0]
        if key_drop_rows_count == 0 and name_drop_rows_count == 0:
            count = 0
        elif key_drop_rows_count >= name_drop_rows_count:
            self.df = self.df[self.df[self.key_field] != 'nan']
            count = key_drop_rows_count
        else:
            self.df = self.df[self.df[self.name_field] != 'nan']
            count = name_drop_rows_count
        logging.info(f"{count} TRASH ROWS WAS DROPPED")

    def _init_df_types(self):
        """на данном этапе все поля в датафрейме - str, а значения NaN - 'nan'
        делаем из 'nan' настоящее а из str - float"""
        self.df = self.df.replace('nan', np.nan)
        logging.debug(f"DECIMAL: {self.config['decimal_fields']}")
        for field in self.config['decimal_fields']:
            try:
                self.df[field] = self.df[field].astype(float)
            except ValueError as e:
                logging.info(f"Value Error on {field}: {e}")
                logging.info("Replacing ',' and ' '")
                self.df[field] = self.df[field].str.replace(' ', '')
                self.df[field] = self.df[field].str.replace(',', '.')
                self.df[field] = self.df[field].astype(float)
            finally:
                # на некоторых значениях вылезал MySQL Warning 1265, "Data truncated for column
                # так как числа хранились иногда в виде "338394.51999999996",
                # который в два десятичных разряда не помещается. Округляем.
                self.df[field] = self.df[field].round(2)

    def _set_index(self):
        """делаем так, чтобы index совпадал с номерами строк в xls"""
        # устанавливаем delta
        self.delta += self.skip
        logging.debug(f'DELTA {self.delta}')
        self.df.index += self.delta

    def _df_autofill(self):
        """автозаполняем некоторые поля, если это необходимо"""
        for field in ['bkf_business_sphere', 'bkf_class_os_code']:
            if field in self.fields:
                df_field = self.fields[field]
                nans_count = self.df[df_field].isnull().sum()
                if nans_count:
                    log = f"FILLING {nans_count} NaN's in {field}"
                    logging.info(log)
                    self.df[df_field] = self.df[df_field].fillna(method='ffill')

    def _mapped_df(self):
        """Оставляем только те поля, которые будут в нашей таблице"""
        self.df = self.df.drop(set(self.df.columns) - set(self.fields), axis=1)
        self.df.columns = [self.mapper[col] for col in self.df.columns]

    def _add_service_fields(self):
        """делаем поля с номером строки, именем файла и названием филиала"""
        self.df['bkf_row_num'] = self.df.index
        self.df['bkf_branch_id'] = self.config['branch_id']
        self.df['bkf_filename'] = self.filename
        self.df.name = self.config['branch_name']

    def parse(self):
        print('Parsing {}...'.format(self.filename))
        self.df = self._findheader()
        # определяем заголовок из нескольких строк, если он есть
        self.multirow = self._find_multirow_header()
        # если индекс многострочный - переписываем его
        if self.multirow:
            self.df = self._rewrite_index()
        # проверяем, все ли поля найдены
        self._mapped()
        # удаляем нумерацию столбцов и прочий мусор в шапке
        self._check_first_string()
        # вычищаем мусор из датафрейма
        self._clear_df()
        # делаем так, чтобы index совпадал с номерами строк в xls
        self._set_index()
        # приводим нужные типы данных
        self._init_df_types()
        # автозаполняем некоторые поля, если это необходимо
        self._df_autofill()
        self._mapped_df()
        self._add_service_fields()
        return self.df
