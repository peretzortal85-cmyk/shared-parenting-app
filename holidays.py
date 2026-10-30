import io, json, re, uuid, zipfile, xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
import streamlit as st
from pyluach import dates

ROOT = Path(__file__).parent
SOURCE = ROOT / 'holiday_source_2027.xlsx'
STATE = ROOT / 'holiday_plans.json'
N = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def read_original():
    with zipfile.ZipFile(SOURCE) as z:
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        mapping={x.attrib['Id']:x.attrib['Target'] for x in rels}
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.text or '' for t in si.iter('{%s}t'%N['m'])) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sheet=next(s for s in workbook.find('m:sheets',N) if s.attrib['name']=='2027')
        path=mapping[sheet.attrib['{%s}id'%N['r']]]
        path=path.lstrip('/') if path.startswith('/') else 'xl/'+path
        xml=ET.fromstring(z.read(path))
        out=[];holiday=''
        for row in xml.findall('.//m:sheetData/m:row',N):
            index=int(row.attrib['r']);
            if index<5: continue
            cells={}
            for cell in row.findall('m:c',N):
                col=re.match('[A-Z]+',cell.attrib['r']).group()
                value=cell.find('m:v',N);inline=cell.find('m:is',N)
                if value is not None:
                    val=shared[int(value.text)] if cell.attrib.get('t')=='s' else value.text
                elif inline is not None:val=''.join(inline.itertext())
                else:val=''
                cells[col]=val
            if cells.get('A','').strip():holiday=cells['A'].strip()
            raw=cells.get('B','').strip()
            if not raw:continue
            try:
                if re.fullmatch(r'\d+(\.\d+)?',raw):day=date(1899,12,30)+timedelta(days=int(float(raw)))
                else:day=datetime.strptime(raw,'%d/%m/%Y').date()
            except (ValueError,OverflowError):continue
            if day.year!=2027:continue
            out.append({'id':f'row{index}','holiday':holiday,'date':day.isoformat(),'day_label':cells.get('C',''),'part':cells.get('D',''),'parent':cells.get('E',''),'notes':cells.get('F','')})
        return out

def load():
    if not STATE.exists():return {}
    try:return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def save(plans):
    # Prototype local file: Streamlit Community Cloud may erase local changes on restart.
    STATE.write_text(json.dumps(plans,ensure_ascii=False,indent=2),encoding='utf-8')

def alternate(p):return {'אב':'אם','אם':'אב'}.get(p,p)

def next_year_date(s,target):
    original=date.fromisoformat(s)
    h=dates.GregorianDate(original.year,original.month,original.day).to_heb()
    # The same Hebrew calendar day in the following civil year; Adar leap cases need review.
    hyear=h.year+(target-2027)
    month=h.month
    try:return dates.HebrewDate(hyear,month,h.day).to_pydate().isoformat()
    except ValueError:
        try:return dates.HebrewDate(hyear,month, min(h.day,29)).to_pydate().isoformat()
        except ValueError:return original.replace(year=target).isoformat()

def new_plan(original,year):
    return {'revision':1,'status':'draft','approved_revision':None,'approved_rows':None,'sent_revision':None,'approval_token':None,'history':[], 'rows':[{**r,'date':next_year_date(r['date'],year),'parent':alternate(r['parent']) if (year-2027)%2 else r['parent']} for r in original]}

def ics(rows,year):
    def esc(s):return str(s).replace('\\','\\\\').replace('\n','\\n').replace(',','\\,').replace(';','\\;')
    parts=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Horut Beyahad//Holiday Plan//HE','CALSCALE:GREGORIAN','X-WR-CALNAME:הורות ביחד']
    # Group only consecutive dates for same parent and holiday, preserving details in description.
    sorted_rows=sorted(rows,key=lambda r:r['date']); groups=[]
    for r in sorted_rows:
        d=date.fromisoformat(r['date'])
        if groups and groups[-1][-1]['parent']==r['parent'] and groups[-1][-1]['holiday']==r['holiday'] and date.fromisoformat(groups[-1][-1]['date'])+timedelta(days=1)==d:
            groups[-1].append(r)
        else:groups.append([r])
    for group in groups:
        first,last=group[0],group[-1]
        start=date.fromisoformat(first['date']);end=date.fromisoformat(last['date'])+timedelta(days=1)
        who='רועי (האב)' if first['parent']=='אב' else 'אורטל (האם)' if first['parent']=='אם' else first['parent']
        description='\n'.join(f"{r['date']} | {r['part']} | {r['notes']}" for r in group)
        parts += ['BEGIN:VEVENT',f'UID:horut-{year}-{first["id"]}@horut-beyahad',f'DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}',f'DTSTART;VALUE=DATE:{start:%Y%m%d}',f'DTEND;VALUE=DATE:{end:%Y%m%d}',f'SUMMARY:{esc("אצל "+who+" — "+first["holiday"])}',f'DESCRIPTION:{esc(description)}','END:VEVENT']
    parts.append('END:VCALENDAR')
    return ('\r\n'.join(parts)+'\r\n').encode('utf-8')

def render():
    st.header('📅 חגים והסדרים')
    st.caption('טבלת 2027 מוצגת מתוך קובץ האקסל המקורי ללא שינוי. שנים חדשות הן הצעות שניתנות לעריכה ולאישור.')
    original=read_original()
    requested=st.query_params.get('holiday_year','2027')
    years=[2027,2028,2029,2030,2031,2032]
    year=st.selectbox('שנת תוכנית',years,index=years.index(int(requested)) if requested.isdigit() and int(requested) in years else 0,key='holiday_year')
    plans=load()
    if year==2027:
        st.info('שנת בסיס: התוכן מועתק לקריאה בלבד מהאקסל המקורי. אין שינוי בקובץ.')
        rows=original
    else:
        key=str(year)
        if key not in plans:
            st.warning(f'טרם נוצרה תוכנית {year}. היא תתבסס על חלוקת 2027 ותהפוך את ההורים לסירוגין. יש לבדוק במיוחד תאריכים, חגים חופפים ושבתות לפני שליחה.')
            if st.button(f'➕ יצירת טיוטת {year}',type='primary'):
                plans[key]=new_plan(original,year);save(plans);st.rerun()
            return
        plan=plans[key];rows=plan['rows']
        statuses={'draft':'טיוטה','sent':'נשלחה לעיון — ממתינה לאישור','approved':'תוכנית מאושרת','changes':'נדרשים תיקונים'}
        st.write(f"**מצב:** {statuses.get(plan['status'],plan['status'])} | **גרסה:** {plan['revision']}")
        st.warning('הנתונים נשמרים כרגע בקובץ מקומי בשרת. בענן Streamlit הם עלולים להימחק באתחול. לפני שימוש מחייב יש להוסיף בסיס נתונים והזדהות לשני ההורים.')
        with st.expander('✏️ עריכת תוכנית החגים',expanded=False):
            st.caption('ערכי את השורות ושמרי. כל שמירה יוצרת גרסה חדשה ומבטלת את תוקף האישור לגבי השינויים החדשים.')
            with st.form('holiday_edit'):
                edited=st.data_editor([{'מזהה':r['id'],'חג':r['holiday'],'תאריך':r['date'],'חלק החג':r['part'],'הורה':r['parent'],'הערות':r['notes']} for r in rows],hide_index=True,use_container_width=True,num_rows='fixed',disabled=['מזהה','חג'],column_config={'הורה':st.column_config.SelectboxColumn('הורה',options=['אב','אם'],required=True),'תאריך':st.column_config.TextColumn('תאריך YYYY-MM-DD',required=True)})
                submit=st.form_submit_button('💾 שמירת שינויים',type='primary')
            if submit:
                try:
                    updated=[]
                    for r in edited.to_dict('records'):
                        d=date.fromisoformat(str(r['תאריך']))
                        if r['הורה'] not in ['אב','אם']:raise ValueError('יש לבחור הורה תקין')
                        updated.append({'id':r['מזהה'],'holiday':r['חג'],'date':d.isoformat(),'day_label':'','part':r['חלק החג'],'parent':r['הורה'],'notes':r['הערות']})
                    if updated!=rows:
                        plan['rows']=updated;plan['revision']+=1;plan['status']='draft';plan['approval_token']=None;plan['sent_revision']=None
                        plan['history'].append({'action':'edit','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
                        save(plans);st.success('נשמרה גרסה חדשה. יש לשלוח אותה מחדש לאישור.');st.rerun()
                    else:st.info('לא זוהו שינויים.')
                except (ValueError,TypeError) as e:st.error(f'תאריך או הורה לא תקין: {e}')
    display=[{'חג':r['holiday'],'תאריך':date.fromisoformat(r['date']).strftime('%d/%m/%Y'),'יום (במקור)':r.get('day_label','') if year==2027 else '', 'חלק החג':r['part'],'שהות':('אצל רועי' if r['parent']=='אב' else 'אצל אורטל' if r['parent']=='אם' else r['parent']),'הערות':r['notes']} for r in rows]
    st.dataframe(display,hide_index=True,use_container_width=True)
    if year==2027:
        st.download_button('📎 הורדת קובץ האקסל המקורי ללא שינוי',SOURCE.read_bytes(),file_name='טבלת סידור חגים 2027.xlsx')
    else:
        st.subheader('📨 שליחת כל התוכנית לרועי לאישור')
        st.caption('WhatsApp פותח הודעה מוכנה. לאחר פתיחת ההודעה צריך ללחוץ שליחה בוואטסאפ בעצמך.')
        if st.button('🔗 הכנת קישור חדש לאישור הגרסה הנוכחית',type='primary'):
            plan['approval_token']=uuid.uuid4().hex;plan['sent_revision']=plan['revision'];plan['status']='sent'
            plan['history'].append({'action':'link_prepared','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
            save(plans);st.rerun()
        if plan.get('approval_token') and plan.get('sent_revision')==plan['revision']:
            base='https://4ktxfrnib3.streamlit.app/'
            link=f"{base}?holiday_year={year}&approval={plan['approval_token']}"
            message=f'רועי, מצורפת תוכנית החגים לשנת {year} (גרסה {plan["revision"]}) לעיונך ולאישור כל התוכנית. אפשר לפתוח, לבדוק את כל התאריכים וחלוקת השהות ולבחור אישור או בקשת תיקונים: {link}'
            st.link_button('📱 פתיחת WhatsApp עם הודעה מוכנה',f'https://wa.me/?text={quote(message)}',use_container_width=True)
            st.code(link,language=None)
            st.caption('הקישור הוא קישור גישה אישי. כל מי שמחזיק בו יכול לבצע פעולה בשלב הניסוי; עדיין אין אימות זהות של רועי.')
        if plan.get('approved_rows'):
            st.success(f"קיימת גרסה מאושרת: {plan['approved_revision']}. אפשר להוריד אותה ליומן Google.")
            st.download_button('📅 הורדת יומן של התוכנית המאושרת (.ics)',ics(plan['approved_rows'],year),file_name=f'horut_approved_{year}.ics',mime='text/calendar')
        if plan.get('history'):
            with st.expander('היסטוריית שינויים ואישורים'):
                st.dataframe(plan['history'],hide_index=True,use_container_width=True)
    st.divider()
    st.subheader('Google Calendar')
    if year==2027:
        st.download_button('📅 הורדת אירועי 2027 ליומן Google (.ics)',ics(rows,year),file_name='horut_2027.ics',mime='text/calendar')
    st.caption('כרגע יש ייצוא לקובץ ICS לייבוא ידני ב-Google Calendar. סנכרון דו-כיווני אוטומטי מחייב הגדרת OAuth ו-Google Calendar API, ואינו מופעל בגרסה זו.')
    # Approval view: token identifies a draft revision but does not authenticate the person opening it.
    if year!=2027:
        params=st.query_params
        token=params.get('approval','')
        if token and token==plan.get('approval_token') and plan.get('sent_revision')==plan['revision']:
            st.subheader('אישור תוכנית שנתית')
            st.write(f"התוכנית המוצגת לעיל היא תוכנית {year}, גרסה {plan['revision']}. האישור חל על כל התוכנית.")
            left,right=st.columns(2)
            if left.button('✅ אני מאשר את כל התוכנית',key='approve_year'):
                plan['approved_rows']=[dict(r) for r in plan['rows']];plan['approved_revision']=plan['revision'];plan['status']='approved';plan['approval_token']=None
                plan['history'].append({'action':'approval_via_link_unverified','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
                save(plans);st.success('נרשם אישור דרך הקישור. זהות המאשר עדיין אינה מאומתת.');st.rerun()
            if right.button('📝 מבקש תיקונים',key='request_changes'):
                plan['status']='changes';plan['approval_token']=None
                plan['history'].append({'action':'changes_requested_via_link_unverified','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
                save(plans);st.rerun()
