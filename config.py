import logging
import pandas as pd
import os
from db import open_db, close_db
from secure import gp_branches_table, bkf_table, \
    startdir, BLACKLIST, bkf_table_comment, branch_table_comment

config_file = 'fields.csv'
ALTER_CONFIG_SUFFIX = '//add'  # суффикс для колонки с альтернативным набором полей
NEW_STRING_SEPARATOR =  '$$'# новая строка в csv конфиге отделяется через $$ чтобы удобнее было набирать


class GpXlsConfig:
    """Считывает файл конфигурации с полями, хранит маппер"""
    def __init__(self, startdir=startdir, csv=config_file, recreate_tables=True):
        """recreate tables позволяет парсить xls по одному в отладочных целях, не удаляя при инициализации
           таблицы, уже загруженные в бд.
        """
        logging.info('INITIALIZE CONFIG')
        branch_config = BranchConfig(startdir, gp_branches_table)
        if recreate_tables:
            logging.info('CREATING BRANCH TABLE')
            branch_config.create_branch_table()
            logging.info('UPLOADING GP_BRANCHES')
            branch_config.fill_gp_branches()
        logging.info(f'LOADING FIELDS CONFIG FROM {csv}')
        fields = pd.read_csv(os.path.join(startdir, csv), sep=';', index_col=0, encoding='cp1251')
        self.fields = fields.applymap(lambda x: x.replace(NEW_STRING_SEPARATOR, '\n') if type(x) == str else x)
        self.branches_indexes = branch_config.branches_indexes
        self.startdir = startdir
        if recreate_tables:
            logging.info('CREATING BKF TABLE')
            self.create_bkf_table()

    def get_config(self, filename):
        branch_name = filename.split(self.startdir)[1].split('/')[1]  # имя верхней папки
        config = self.get_branch_fields(branch_name)
        config['branch_name'] = branch_name
        config['branch_id'] = self.branches_indexes[branch_name]
        config['is_alter'] = False
        return config

    def get_alter_config(self, filename):
        """У некоторых филиалов поля в файлах отличаются. Поэтому приходится держать альтернативную конфигурацию"""
        branch_name = filename.split(self.startdir)[1].split('/')[1]  # имя верхней папки
        config = self.get_branch_fields(branch_name + ALTER_CONFIG_SUFFIX)
        config['branch_name'] = branch_name
        config['branch_id'] = self.branches_indexes[branch_name]
        config['is_alter'] = True
        return config

    def get_branch_fields(self, branch_name):
        branch_fields = self.fields[branch_name].dropna()
        config = {
            'key_field': self.fields[branch_name]['bkf_inv_num'],
            'name_field': self.fields[branch_name]['bkf_os_name'],
            'fields': branch_fields,
            'mapper': {v: k for k, v in branch_fields.items()},  # словарь -  русское назв.: англ назв.
            'decimal_fields': [self.fields[branch_name][f] for f in branch_fields.index
                               if 'decimal' in self.fields['TYPE'][f].lower()],
        }
        return config

    def create_bkf_table(self):
        cur, conn = open_db()
        cur.execute(f"""DROP TABLE IF EXISTS `{bkf_table}`""")
        HEAD = f"""
        CREATE TABLE `{bkf_table}` (
            `bkf_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            `bkf_branch_id` int(11) DEFAULT NULL COMMENT 'id из gp_branches',  
        """
        TAIL = """,
            `bkf_row_num` int(11) DEFAULT NULL COMMENT 'Номер строки в файле',
            `bkf_filename` varchar(255) DEFAULT NULL COMMENT 'Имя файла',
             PRIMARY KEY (`bkf_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci COMMENT='{}';
        """.format(bkf_table_comment)

        fields_sql = [f"    `{ix}` {field['TYPE']} DEFAULT NULL COMMENT '{field['DESCRIPTION']}'"
                      for ix, field in self.fields.iterrows()]
        fields_sql = ',\n'.join(fields_sql)
        SQL = HEAD + fields_sql + TAIL
        cur.execute(SQL)
        conn.commit()
        close_db(cur, conn)


class BranchConfig:
    def __init__(self, startdir, gp_branches_table):
        self.startdir = startdir
        self.gp_branches_table = gp_branches_table

    def create_branch_table(self):
        cur, conn = open_db()
        cur.execute(f"""DROP TABLE IF EXISTS `{self.gp_branches_table}`""")
        SQL = f"""
        CREATE TABLE `{self.gp_branches_table}` (
            `gpb_id` int(11) NOT NULL AUTO_INCREMENT,
            `gpb_name` varchar(255) NOT NULL,
             PRIMARY KEY (`gpb_id`),
             UNIQUE KEY `name` (`gpb_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci COMMENT='{branch_table_comment}';
        """
        cur.execute(SQL)
        conn.commit()
        close_db(cur, conn)

    def fill_gp_branches(self):
        branches = [e.name for e in os.scandir(startdir) if e.is_dir() and not e.name.startswith('.')]
        cur, conn = open_db()
        for branch in branches:
            SQL = f"""INSERT INTO {self.gp_branches_table} (gpb_name) VALUES('{branch}');"""
            cur.execute(SQL)
        conn.commit()
        close_db(cur, conn)

    @property
    def branches_indexes(self):
        """здесь делается селект, так как это поле запрашивается в скрипте только однажды"""
        cur, conn = open_db()
        SQL = f"""SELECT * FROM {self.gp_branches_table}"""
        cur.execute(SQL)
        branches_indexes = {br['gpb_name']: br['gpb_id'] for br in cur}
        close_db(cur, conn)
        return branches_indexes
