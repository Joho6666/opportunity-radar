def test_split_never_leaks_original_or_repost_group():
    from app.services.label_dataset import partition
    rows=[{"id":str(i),"group_id":str(i//2),"text":"sample "+str(i),"category":"buyer","human_label":True} for i in range(260)]
    result=partition(rows)
    owners={}
    for name,data in result.items():
        for row in data:
            assert row["group_id"] not in owners or owners[row["group_id"]] == name
            owners[row["group_id"]]=name
    assert result == partition(rows)


def test_unreviewed_or_synthetic_rows_cannot_enter_training():
    from app.services.label_dataset import partition
    import pytest
    with pytest.raises(ValueError):
        partition([{"id":"1","group_id":"1","text":"sample","category":"buyer","human_label":False}])


def test_shared_source_url_and_identical_text_stay_in_one_split():
    from app.services.label_dataset import partition,split_leakage
    rows=[{'id':str(i),'group_id':str(i),'text':'unique '+str(i),'category':'market','human_label':True,'source_url':'https://example.test/'+str(i)} for i in range(260)]
    rows[-1]['source_url']=rows[0]['source_url']
    rows[-2]['text']=rows[1]['text']
    splits=partition(rows)
    assert not split_leakage(splits)
    assert split_leakage({'train':[rows[0]],'holdout':[rows[-1]]})
