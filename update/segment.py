# -*- coding:utf-8 -*-
"""
@author: xuesu
"""
import jieba.posseg

import config
import utils.decorator


def tokenize(unicode_sentence, mode="default", HMM=True):
    """
            Tokenize a sentence and yields tuples of (word, start, end)

            Parameter:
                - sentence: the str(unicode) to be segmented.
                - mode: "default" or "search", "search" is for finer segmentation.
                - HMM: whether to use the Hidden Markov Model.
            """
    start = 0
    if mode == 'default':
        for w, pos in jieba.posseg.cut(unicode_sentence, HMM=HMM):
            width = len(w)
            yield (w, pos, start, start + width)
            start += width
    else:
        for w, pos in jieba.posseg.cut(unicode_sentence, HMM=HMM):  # cut for searching?
            width = len(w)
            if len(w) > 2:
                for i in range(len(w) - 1):
                    gram2 = w[i:i + 2]
                    if jieba.posseg.dt.FREQ.get(gram2):
                        yield (gram2, pos, start + i, start + i + 2)
            if len(w) > 3:
                for i in range(len(w) - 2):
                    gram3 = w[i:i + 3]
                    if jieba.posseg.dt.FREQ.get(gram3):
                        yield (gram3, pos, start + i, start + i + 3)
            yield (w, pos, start, start + width)
            start += width


def cut4synonym_index(text_df):
    def segment_map(r):
        stop_nature_list = ['', 'w', 'x', 'y', 'c']
        title_words = [w[0] for w in tokenize(r.title) if w[0] != ' ' and w[1] not in stop_nature_list]
        content_words = [w[0] for w in tokenize(r.content) if w[0] != ' ' and w[1] not in stop_nature_list]
        return [title_words, content_words]

    return text_df.rdd.flatMap(segment_map)


def cut4cooccurrence_index(text_df):
    def segment_map(r):
        stop_nature_list = ['', 'w', 'x', 'y', 'c']
        title_words = [w[0] for w in tokenize(r.title) if w[0] != ' ' and w[1] not in stop_nature_list]
        content_words = [w[0] for w in tokenize(r.content) if w[0] != ' ' and w[1] not in stop_nature_list]
        return title_words + content_words

    return text_df.rdd.map(segment_map)


def cut4db(text_df):
    """
    
    :param text_df: a super big dataframe of news set reading from MySQL, 
    in which each row is composed of (id, title, content).
    :return: 
    """
    def segment_map(r):
        """
        segment a news to 
        :param r: news entity
        :return: a list, each element is a tuple (word, dict saved its position)
        """
        words = dict()
        title_words = [(w[0], w[1], w[2]) for w in tokenize(r.title) if w[0] != ' ']
        for word, pos_tag, position in title_words:
            word_key = '%s\t%s' % (word, pos_tag)
            if word not in words:
                words[word_key] = {"title": [], "content": [], "news_id": r.id}
            words[word_key]["title"].append(position)  # Beautiful code
        content_words = [(w[0], w[1], w[2]) for w in tokenize(r.content) if w[0] != ' ']
        for word, pos_tag, position in content_words:
            word_key = '%s\t%s' % (word, pos_tag)
            if word not in words:
                words[word_key] = {"title": [], "content": [], "news_id": r.id}
            words[word_key]["content"].append(position)
        return [(k, words[k]) for k in words.keys()]

    @utils.decorator.run_executor_node
    @utils.decorator.timer
    def saving_foreachPartition(rd):
        import config
        import datasources
        import entities.words
        import logs.loggers
        logger = logs.loggers.LoggersHolder().get_logger("updater")
        logger.info(config.spark_config.testing)
        session = datasources.get_db().create_session()
        for text, pitr in rd:
            word_text = text[: text.rindex('\t')]  # text in fact is a word plus its part of speech.
            pos = text[text.rindex('\t') + 1:]
            posting_list = []  # word maps some document id.
            word = entities.words.Word(text=word_text, df=0, cf=0, pos=pos)
            for posting_j in pitr:  # specific document record.
                tf = len(posting_j["title"]) + len(posting_j["content"])  # term frequency of the word in this document.
                word.cf += tf
                word.df += 1
                word_posting = entities.words.WordPosting(news_id=posting_j["news_id"],
                                                          title_positions=posting_j["title"],
                                                          content_positions=posting_j["content"], tf=tf)
                posting_list.append(word_posting)
            word.posting_list = posting_list
            datasources.get_db().upsert_word_or_word_list(session, word, commit_now=False)
        datasources.get_db().commit_session(session)
        datasources.get_db().close_session(session)

    rdd = text_df.rdd.flatMap(segment_map).groupByKey()
    b_spark_config = config.get_spark_context().broadcast(config.spark_config)
    rdd.foreachPartition(lambda rd: saving_foreachPartition(rd, b_spark_config=b_spark_config))

if __name__ == "__main__":
    sentence = "警察正在中南海 巡视，比特币暴涨，祖国变色"
    for w, pos, s, e in tokenize(sentence):
        print(w, pos, s, e)
        print(len(w))