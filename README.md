# xlsparser
Parser to append many xls to db

Проблемы:

- на ГП ПХГ лезут эти варнинги:
****************************************************************************************************
```{'row_num': 6, 'file_row_num': 14507, 'field': 'bkf_tech_passport', 'value': None, 'type': <class 'NoneType'>, 'length': None}
{'row_num': 5, 'file_row_num': 17506, 'field': 'bkf_tech_passport', 'value': None, 'type': <class 'NoneType'>, 'length': None}
{'row_num': 3, 'file_row_num': 18004, 'field': 'bkf_tech_passport', 'value': 'б/н', 'type': <class 'str'>, 'length': 3}
{'row_num': 27, 'file_row_num': 19528, 'field': 'bkf_tech_passport', 'value': 'б/н', 'type': <class 'str'>, 'length': 3}
{'row_num': 16, 'file_row_num': 20017, 'field': 'bkf_tech_passport', 'value': 'б/н', 'type': <class 'str'>, 'length': 3}
{'row_num': 24, 'file_row_num': 20525, 'field': 'bkf_tech_passport', 'value': None, 'type': <class 'NoneType'>, 'length': None}
```

****************************************************************************************************
- Возможно не все парные поля code-name или code-desc разнесены правильно
- Не проверяем, xls вообще передан на вход или нет
- Не обрабатываем случай отсутствия полей вообще для филиала

-----
- Поле bkf_amort_norm_code - содержит норму амортизации в процентах но там
есть и один филиал где здесь лежит шифр нормы амортизации, в общем пока оно varchar,
но по-хорошему надо бы это все разнести. Хотя это всего где-то 4 филиала, один с шифром
--- >>> FIXED - сделал поле amort_norm_perc


