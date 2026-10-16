class MultiSelectSave(object):
    def __init__(self,
                 dict_obj: dict,
                 key_name: str,
                 max_len: int):
        self.key_name = key_name
        self.dict_obj = dict_obj
        self.max_len = max_len

    def __len__(self):
        return self.max_len

    def __getitem__(self, idx):
        key = f'{self.key_name}_{idx}'
        assert idx <= self.max_len, \
            f'Index out of range: max_len={self.max_len} you give: {idx}'

        assert key in self.dict_obj.keys(), \
            f'the key({key}) not in the dict_obj'
        return self.dict_obj[key]

    def __setitem__(self, idx, val):
        key = f'{self.key_name}_{idx}'
        assert idx <= self.max_len, \
            f'Index out of range: max_len={self.max_len} you give: {idx}'

        assert key in self.dict_obj.keys(), \
            f'the key({key}) not in the dict_obj'
        self.dict_obj[key] = val

    # # for looping
    # def __iter__(self):
    #     return self
    # and
    # def __next__(self):
    # src: https://www.programiz.com/python-programming/iterator

    def __iter__(self):
        for idx in range(self.max_len):
            yield self.__getitem__(idx).copy()


if __name__ == "__main__":

    dict_obj = {
        'hamo_0': {'id': 1, 'val': 3},
        'hamo_1': {'id': 9, 'val': 5},
    }
    m_obj = MultiSelectSave(dict_obj, 'hamo', 2)

    # get method
    print('Test Get Method')
    for i in range(len(m_obj)):
        print(m_obj[i])

    # set_method
    print('\n\nTest set Method')
    for i in range(len(m_obj)):
        m_obj[i]['id'] = m_obj[i]['id'] * 10
        m_obj[i]['val'] = m_obj[i]['val'] * 10

        print(dict_obj[f'hamo_{i}'])

    print('\n\n\nUsing iterators')
    print('Test Get Method')
    for item in m_obj:
        print(item)

    # set_method
    print('\n\nTest set Method')
    for item in m_obj:
        item['id'] = item['id'] * 9
        item['val'] = item['val'] * 9

        print(dict_obj[f'hamo_{i}'])

    # print('Out of range Error')
    # print(m_obj[4])

    print('Ivalid key')
    print(MultiSelectSave(dict_obj, 'nono', 4)[0])
