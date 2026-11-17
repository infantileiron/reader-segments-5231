from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,Index
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Reader(Base):
 __tablename__='readers'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);weekly_reading=Column(Float);completion=Column(Float);night_share=Column(Float);note=Column(Text,default='')
class Segment(Base):
 __tablename__='segments'
 id=Column(Integer,primary_key=True);name=Column(String(100));k=Column(Integer);features=Column(JSON);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')
class Outreach(Base):
 __tablename__='outreaches'
 id=Column(Integer,primary_key=True);segment_id=Column(Integer,ForeignKey('segments.id'));cluster_id=Column(Integer);title=Column(String(100));note=Column(Text);members=Column(JSON);status=Column(String(20),default='draft')
 parent_outreach_id=Column(Integer,ForeignKey('outreaches.id'))
 root_outreach_id=Column(Integer,ForeignKey('outreaches.id'),index=True)
 resend_for_batch_id=Column(Integer,index=True)
 created=Column(String(40),default='')
 receipt_watermark=Column(JSON,default=dict)
class ReconBatch(Base):
 __tablename__='recon_batches'
 id=Column(Integer,primary_key=True)
 outreach_id=Column(Integer,ForeignKey('outreaches.id'),nullable=False,unique=True)
 root_outreach_id=Column(Integer,nullable=False,index=True)
 state=Column(String(20),default='pending')
 roster=Column(JSON,nullable=False)
 roster_checksum=Column(String(64),nullable=False)
 summary=Column(JSON)
 resend_outreach_id=Column(Integer)
 note=Column(Text,default='')
 created=Column(String(40))
 settled_at=Column(String(40),default='')
class Receipt(Base):
 __tablename__='receipts'
 id=Column(Integer,primary_key=True)
 batch_id=Column(Integer,ForeignKey('recon_batches.id'),nullable=False,index=True)
 channel=Column(String(40),nullable=False)
 channel_key=Column(String(40),nullable=False)
 serial=Column(String(80),nullable=False)
 member=Column(String(60),nullable=False)
 occurred_at=Column(String(40),nullable=False)
 result=Column(String(20),nullable=False)
 fingerprint=Column(String(64),nullable=False)
 state=Column(String(20),default='accepted')
 reason=Column(String(40),default='')
 received_at=Column(String(40))
 occurrences=Column(Integer,default=1)
 __table_args__=(Index('ix_receipts_batch_fingerprint','batch_id','fingerprint'),Index('ix_receipts_batch_serial','batch_id','channel_key','serial'),Index('ix_receipts_batch_member','batch_id','member'))
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
