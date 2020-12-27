#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @Time  : 2020-12-27, 0027 14:49
# @Author: 佚名
# @File  : myself_task.py
import json
import gc
import re
import requests
import sys
import time
from .cdr_task import CDRTask
from ..utils import settings, Answer, Course, Log, Tool
from ..config import CDR_VERSION, CONFIG_DIR_PATH


class MyselfTask(CDRTask):
    
    def __init__(self, course_id):
        self.__course_id = course_id
    
    def run(self):
        time_out = settings.timeout
        course_id = self.__course_id
        is_random_score = settings.is_random_score
        task_list, json_data = MyselfTask.get_task_list(course_id)
        Tool.cls()
        while True:
            Log.v("请输入序号去选择要做的任务：\n")
            Log.v(f"{json_data['course_name']}\n当前进度：{json_data['progress']}%\n"
                  + f"累计用时：{Tool.convert_time(json_data['time_spent'])}")
            for i, task in enumerate(task_list):
                Log.v(f"{i + 1:2d}. {task['task_name']:20s} [{task['progress']}%]（{task['score']:2.1f}分）")
            Log.v("\n#.  以空格分割可一次性选择多个任务")
            Log.v(f"#.  你可以在“main{CONFIG_DIR_PATH[1:]}config.txt文件”中修改配置项以控分/修改做题时间间隔等")
            Log.v("\n\n0.  选择全部任务\n\n请输入序号：", end="")
            choose = ' '.join(input("").split()).split(" ")
            Log.v(choose, is_show=False)
            task_choose_list = []
            tem_flag = True
            if CDRTask.check_input_data(choose[0], 0):
                task_choose_list = task_list
            else:
                for c in choose:
                    if not CDRTask.check_input_data(c, len(task_list)):
                        tem_flag = False
                        Tool.cls()
                        Log.i("输入格式有误！\n")
                        break
                    task_choose_list.append(task_list[int(c) - 1])
            if tem_flag:
                break
        for i in task_choose_list:
            # 未过期任务
            #   over_status为任务标识，1：未开始 2：进行中 3：已过期
            #   task_id仅作为辅助标识，若任务是多单元混合，其为-1，若是单独，则其为对应课程号
            #   task_type为任务类型标识（未证实） 1：学习任务 2：测试任务
            if i["score"] != 100:
                task_id = i["task_id"]
                now_score = CDRTask.get_random_score(is_open=is_random_score)
                Log.i("course_id:" + course_id, is_show=False)
                Log.i("开始做【" + i["task_name"] + "】，目标分数：" + str(now_score))
                answer = Answer(Course(course_id))
                Log.i("题库装载完毕！")
                count = 0
                while True:
                    count += 1
                    if count > 3:
                        Log.i("相同任务重复答题次数过多，疑似存在无法找到答案的题目，自动跳过本任务")
                        break
                    Log.i("模拟加载流程")
                    #   模拟加载流程
                    res = requests.get(url=f"https://gateway.vocabgo.com/Student/StudyTask/Info?task_id={task_id:d}"
                                       f"&course_id={i['course_id']}&list_id={i['list_id']}"
                                       f"&timestamp={Tool.time()}&versions={CDR_VERSION}",
                                       headers=settings.header, timeout=time_out)
                    json_data = res.json()
                    res.close()
                    task_id = json_data["data"]["task_id"]
                    grade = json_data["data"]["grade"]
                    time.sleep(1)
                    res = requests.get(url="https://gateway.vocabgo.com/Student/StudyTask/StartAnswer?task_id="
                                           f"{task_id:d}&task_type={i['task_type']:d}&course_id={i['course_id']}"
                                           f"&list_id={i['list_id']}&grade={grade:d}"
                                           f"&timestamp={Tool.time()}&versions={CDR_VERSION}",
                                           headers=settings.header, timeout=time_out)
                    json_data = res.json()
                    res.close()
                    if json_data['code'] == 10017:
                        Log.i("\n" + json_data['msg'])
                        Log.i("注：该限制为词达人官方行为，与作者无关\n按回车退出程序")
                        input()
                        sys.exit(0)
                    Log.i("自选-学习任务")
                    #   判断是否需要选词
                    if json_data["code"] == 20001 and MyselfTask.choose_word(i, task_id, grade):
                        break
                    # 开始任务包
                    timestamp = Tool.time()
                    data = {
                        "task_id": task_id,
                        "task_type": i["task_type"],
                        "course_id": i["course_id"],
                        "list_id": i["list_id"],
                        "grade": grade,
                        "timestamp": timestamp,
                        "versions": CDR_VERSION
                    }
                    res = requests.get(url='https://gateway.vocabgo.com/Student/StudyTask/StartAnswer',
                                       headers=settings.header, params=data, timeout=time_out)
                    json_data = res.json()
                    res.close()
                    time.sleep(1)
                    if json_data["code"] == 0 and json_data["msg"] is not None \
                            and json_data["msg"].find("返回首页") != -1:
                        Log.i("任务信息加载失败，返回上一级重选任务即可")
                        input("按回车返回上一级")
                        return
                    #   判断是否跳过学习阶段
                    Log.i(json_data, is_show=False)
                    if json_data["data"]["topic_mode"] == 0:
                        json_data = MyselfTask.skip_learn_task(json_data["data"]["topic_code"])
                        Log.i("已跳过学习阶段")
                    Log.i("开始答题\n")
                    if json_data["code"] == 0:
                        Log.i(json_data["msg"])
                        return
                    # 提交做题
                    #   code=20004时代表当前题目已做完，测试任务完成标志
                    #   code=20001需要选词，学习任务完成标志
                    while json_data["code"] != 20004 and json_data["code"] != 20001 and \
                            json_data["data"]["topic_done_num"] <= json_data["data"]["topic_total"]:
                        json_data = MyselfTask.do_question(answer, json_data, course_id, i['list_id'], now_score)
                    Log.i(f"【{i['task_name']}】已完成。分数"
                          f"{MyselfTask.get_myself_task_score(course_id, i['list_id'])}")
                    if json_data["code"] == 20004:
                        break
                    if now_score <= MyselfTask.get_myself_task_score(course_id, i['list_id']):
                        break
            else:
                Log.i(f"该【{i['task_name']}】任务已满分")
        Log.i("本次全部任务已完成！")
        input("按回车键返回上一级")

    @staticmethod
    def get_task_list(course_id):
        time_out = settings.timeout
        requests.options(
            url=f'https://gateway.vocabgo.com/Student/StudyTask/List?course_id={course_id}&timestamp={Tool.time()}'
                + f'&versions={CDR_VERSION}', headers=settings.header, timeout=time_out).close()
        res = requests.get(
            url=f'https://gateway.vocabgo.com/Student/StudyTask/List?course_id={course_id}&timestamp={Tool.time()}'
                + f'&versions={CDR_VERSION}', headers=settings.header, timeout=time_out)
        json_data = res.json()['data']
        Log.i(json_data, is_show=False)
        res.close()
        return json_data['task_list'], json_data

    @staticmethod
    def get_task_id(task_id: int, release_id: int) -> int:
        count = 0
        while task_id == -1 and count < 5:
            res = requests.get(f"https://gateway.vocabgo.com/Student/StudyTask/Info?task_id={task_id:d}"
                               f"&release_id={release_id:d}&timestamp={Tool.time()}&versions={CDR_VERSION}",
                               headers=settings.header, timeout=settings.timeout)
            json_data = res.json()
            res.close()
            if json_data["code"] == 1:
                task_id = json_data["data"]["task_id"]
            Log.i(f"task_id:{task_id:d},count:{count:d}", is_show=False)
            count = count + 1
        return task_id

    @staticmethod
    def choose_word(task: dict, task_id: int, grade: int) -> bool:
        time_out = settings.timeout
        Log.i("需要选词")
        res = requests.get(
            url=f"https://gateway.vocabgo.com/Student/StudyTask/ChoseWordList?task_id={task_id:d}"
                f"&course_id={task['course_id']}&list_id={task['list_id']}&grade={grade:d}&timestamp="
                f"{Tool.time()}&versions={CDR_VERSION}",
            headers=settings.header, timeout=time_out)
        json_data = res.json()
        res.close()
        word_map = {}
        for word in json_data['data']['word_list']:
            if word['score'] != 10:
                tem_str = task['course_id'] + ':' + word["list_id"]
                if word_map.get(tem_str) is None:
                    word_map[tem_str] = []
                word_map[tem_str].append(word['word'])
        if len(word_map) == 0:
            Log.i("当前学习任务以完成")
            return True
        Log.i(word_map, is_show=False)
        tem_i = 0
        tem_len = 0
        for k in word_map:
            tem_len += len(word_map[k])
        while tem_len < 5:
            tem_o = json_data['data']['word_list'][tem_i]
            tem_str = task['course_id'] + ':' + tem_o["list_id"]
            if tem_o['word'] not in word_map[tem_str]:
                if word_map.get(tem_str) is None:
                    word_map[tem_str] = []
                word_map[tem_str].append(tem_o['word'])
                Log.i(f"单词复选：{tem_o['word']}", is_show=False)
            tem_i = tem_i + 1

            tem_len = 0
            for k in word_map:
                tem_len += len(word_map[k])
        Log.i(word_map, is_show=False)
        timestamp = Tool.time()
        sign = Tool.md5(f'task_id={task_id}&timestamp={timestamp}&versions={CDR_VERSION}&word_map='
                        + json.dumps(word_map, separators=(',', ':')).replace("'", '"')
                        + 'ajfajfamsnfaflfasakljdlalkflak')
        data = {
            "task_id": task_id,
            "word_map": word_map,
            "timestamp": timestamp,
            "versions": CDR_VERSION,
            "sign": sign
        }
        res = requests.post(
            url='https://gateway.vocabgo.com/Student/StudyTask/SubmitChoseWord',
            headers=settings.header, json=data, timeout=time_out)
        Log.i(res.json(), is_show=False)
        res.close()
        Log.i("选词完毕！")
        return False

    @staticmethod
    def skip_learn_task(topic_code: str):
        #   模拟加载流程
        Log.i("正在跳过学习任务的学习阶段")
        timestamp = Tool.time()
        time_spent = 0
        sign = Tool.md5(f"time_spent={time_spent}&timestamp={timestamp}&topic_code={topic_code}"
                        f"&versions={CDR_VERSION}ajfajfamsnfaflfasakljdlalkflak")
        data = {
            "topic_code": topic_code,
            "time_spent": time_spent,
            "timestamp": timestamp,
            "versions": CDR_VERSION,
            "sign": sign
        }
        res = requests.post(
            url='https://gateway.vocabgo.com/Student/StudyTask/SubmitAnswerAndSave',
            json=data, headers=settings.header, timeout=settings.timeout)
        json_data = res.json()
        res.close()
        time.sleep(1)
        #   流程模拟结束
        timestamp = Tool.time()
        sign = Tool.md5(f"timestamp={timestamp}&topic_code={json_data['data']['topic_code']}"
                        f"&versions={CDR_VERSION}ajfajfamsnfaflfasakljdlalkflak")
        data = {
            "topic_code": json_data['data']['topic_code'],
            "timestamp": timestamp,
            "versions": CDR_VERSION,
            "sign": sign
        }
        res = requests.post(
            url='https://gateway.vocabgo.com/Student/StudyTask/SkipNowTopicMode',
            json=data, headers=settings.header, timeout=settings.timeout)
        json_data = res.json()
        res.close()
        return json_data

    @staticmethod
    def get_myself_task_score(course_id, list_id):
        requests.options(
            url='https://gateway.vocabgo.com/Student/StudyTask/List?course_id=' + course_id + '&timestamp='
                + f'{Tool.time()}&versions={CDR_VERSION}', headers=settings.header, timeout=settings.timeout).close()
        res = requests.get(
            url='https://gateway.vocabgo.com/Student/StudyTask/List?course_id=' + course_id + '&timestamp='
                + f'{Tool.time()}&versions={CDR_VERSION}', headers=settings.header, timeout=settings.timeout)
        json_data = res.json()
        res.close()
        for task in json_data['data']['task_list']:
            if task["list_id"] == list_id:
                return task["score"]
        return 0

    @staticmethod
    def do_question(answer: Answer, json_data: dict, course_id, list_id, now_score) -> dict:
        Log.i(str(json_data["data"]["topic_done_num"])
              + "/" + str(json_data["data"]["topic_total"]) + ".", end='')
        if now_score != 100 and 100.0 * json_data["data"]["topic_done_num"] / \
                json_data["data"]["topic_total"] + 5 >= now_score:
            if not settings.r["isRandomTime"]:
                time.sleep(0.1)
            else:
                time.sleep(2)
            if MyselfTask.get_myself_task_score(course_id, list_id) >= now_score:
                Log.i(f"[mode:{json_data['data']['topic_mode']}]{json_data['data']['stem']['content']}"
                      + "   已达本次既定分数，超时本题！")
                json_data = CDRTask.skip_answer(json_data["data"]["topic_code"],
                                                json_data["data"]["topic_mode"], "StudyTask")
            else:
                json_data = CDRTask.find_answer_and_finish(answer, json_data["data"], 0)
        else:
            json_data = CDRTask.find_answer_and_finish(answer, json_data["data"], 0)
        #   每10道题清理一次gc
        if json_data.get("data") is None:
            Log.i(json_data)
        if json_data["code"] == 1 and json_data["data"]["topic_done_num"] % 10 == 0:
            requests.session().keep_alive = False
            gc.collect()
            gc.set_debug(gc.DEBUG_UNCOLLECTABLE)
        return json_data