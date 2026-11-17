from pydantic import BaseModel,Field,field_validator
from typing import Literal
from src.utils.clock import normalize_occurred_at
class Login(BaseModel):email:str;password:str
class ReaderInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 weekly_reading:float=Field(ge=0,le=1000,allow_inf_nan=False)
 completion:float=Field(ge=0,le=1,allow_inf_nan=False)
 night_share:float=Field(ge=0,le=1,allow_inf_nan=False)
 note:str=Field(default='',max_length=1000)
class SegmentInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 k:int=Field(default=3,ge=2,le=6)
 features:list[Literal['weekly_reading','completion','night_share']]=Field(default=['weekly_reading','completion','night_share'],min_length=2,max_length=3)
 @field_validator('features')
 @classmethod
 def unique(cls,v):
  if len(set(v))!=len(v):raise ValueError('特征不能重复')
  return v
class OutreachInput(BaseModel):
 segment_id:int=Field(gt=0)
 cluster_id:int=Field(ge=0,le=5)
 title:str=Field(min_length=2,max_length=100)
 note:str=Field(min_length=8,max_length=2000)
class ReceiptInput(BaseModel):
 channel:str=Field(min_length=1,max_length=40)
 serial:str=Field(min_length=1,max_length=80)
 member:str=Field(min_length=1,max_length=60)
 occurred_at:str=Field(min_length=10,max_length=40)
 result:Literal['delivered','bounced']
 @field_validator('channel','serial','member')
 @classmethod
 def strip_text(cls,value):
  text=value.strip()
  if not text:raise ValueError('渠道、流水号与会员编号不能为空白')
  return text
 @field_validator('occurred_at')
 @classmethod
 def valid_time(cls,value):return normalize_occurred_at(value)
class BatchInput(BaseModel):
 outreach_id:int=Field(gt=0)
 note:str=Field(default='',max_length=1000)
class SettleInput(BaseModel):
 receipts:list[ReceiptInput]=Field(default_factory=list,max_length=2000)
 note:str=Field(default='',max_length=1000)
