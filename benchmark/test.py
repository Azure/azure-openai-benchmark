import time
import os
import aiohttp
import wonderwords
import math
import logging
from typing import Iterable, Iterator
from .oaitokenizer import num_tokens_from_messages

import sys

CACHED_PROMPT=""
CACHED_MESSAGES_TOKENS=0
def _generate_messages(model:str, tokens:int, max_tokens:int=None) -> ([dict], int):
   """
   Generate `messages` array based on tokens and max_tokens.
   Returns Tuple of messages array and actual context token count.
   """
   global CACHED_PROMPT
   global CACHED_MESSAGES_TOKENS
   input_message = """
   你现在需要同时扮演一个购买汽车的用户和4s店专业汽车销售员。以下数据提供的是一篇汽车新闻数据，购买汽车的用户提出新闻中涉及的汽车相关问题，汽车销售需要根据给定的数据和专业知识进行回答,需要生成多轮问答对。生成的对话内容请注意以 下要点：1. 数据中的专有名词转为更人性化的常见表达；2. 用户提出的问题要具备完整性和多样性，第一组问题应包含车辆名称，多轮问题之间有上下文关联性；3. 销售的回答要语义流畅且完整, 生成的文本不能超出给定的数据范围。4. 对于用户的抽象类问题，如"是否值得购买"或者"是否智能化"等类问题应该根据车型的具体配置进行回答。5.最终结果输出到一个json格式中，示例：[{"user": "xx问题", "assistant": "xx答案"}, {"user": "xx问题", "assistant": "xx答 案"}]\n新闻数据:\n```{"text": "现在关于网上传的非常火热的“丰田机油门”事件，可谓是火遍了各大网络平台，就在消费者开始怀疑丰田的稳定性时，国内的 一汽丰田官方在3月12日正式 站出来做了回复。\n但其实他也没有否认这件事的存在，从它公布的数据来看，今年的2月份到3月11日期间，此次事件一汽丰田一共涉及到249台问题车辆，其中有64台RAV4荣放和185台亚洲龙，对于这些投诉，一汽丰田给出机油液面上升的解释有四点。\n一个就是在车辆出厂前，发动机工厂会以机油最高点，即机油尺F线注入机油
，但是会有一定的公差存在，实际可能机油液面会比F线更高。\n第二个就是在车辆后期的维修保养时，机油也有可能会加过高液面。\n第三点是发动机在低温冷 启动
的时候，未经正常燃烧的汽油确实是有可能经过活塞环进入机油里的。\n第四点是机油尺上的测量液面是有可能因为地面坡度、机油温度等因素而变得不一样的，就很
有可能会出现机油增多的现象。\n另外针对网上出现的机油乳化现象，一汽丰田给出的解释是，在发动机没有经过充分暖机的情况下，或者是在经常性的低速段距离行
驶时，发动机内部会有少量的结露水不能蒸发进而混合在发动机机油当中，于是在机油口附近便会出现乳化现象。\n在经过发动机的充分暖机之后，机油温度上升，水
分蒸发，乳化现象就会消失。也就是说一汽丰田认为这次的机油乳化问题与丰田本身的质量并无关联，那么你认同它这种说法吗？\n声明：本文图片来源于网络，版权归原作者所有，侵权删\n"}
   """
   try:
      r = wonderwords.RandomWord()
      messages = [{"role":"user", "content":str(time.time()) + input_message}]
      messages_tokens = num_tokens_from_messages(messages, model)
   except Exception as e:
      print (e)
   return (messages, messages_tokens)

messages, messages_tokens = _generate_messages('gpt-4-0613', 1000, 500)
print(messages)
print(messages_tokens)
