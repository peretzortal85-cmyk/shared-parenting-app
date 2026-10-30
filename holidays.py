import io, json, re, uuid, zipfile, html, xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
import streamlit as st
from pyluach import dates, hebrewcal

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
    hyear=h.year+(target-2027)
    source_leap=hebrewcal.Year(h.year).leap
    target_leap=hebrewcal.Year(hyear).leap
    month=h.month
    # Pyluach: Adar=12 in common years; Adar I=12, Adar II=13 in leap years.
    # Purim (Adar II) must map to ordinary Adar in a non-leap year.
    if source_leap and not target_leap and month==13:
        month=12
    elif not source_leap and target_leap and month==12:
        month=13
    try:
        return dates.HebrewDate(hyear,month,h.day).to_pydate().isoformat()
    except ValueError:
        # A 30th day can disappear in the target year. Flag via fallback;
        # the resulting plan remains a draft requiring review.
        try:return dates.HebrewDate(hyear,month,min(h.day,29)).to_pydate().isoformat()
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

def export_plan_xlsx(rows, year, revision):
    # Export currently edited plan as formatted RTL XLSX without changing the source.
    from xml.sax.saxutils import escape
    columns = ['חג', 'תאריך', 'יום', 'חלק החג', 'שהות', 'הערות']
    weekdays = ['יום שני','יום שלישי','יום רביעי','יום חמישי','יום שישי','יום שבת','יום ראשון']
    table = [columns]
    for r in rows:
        d = date.fromisoformat(r['date'])
        table.append([str(r.get('holiday','')), d.strftime('%d/%m/%Y'), weekdays[d.weekday()],
                      str(r.get('part','')), 'אצל רועי (האב)' if r.get('parent') == 'אב' else 'אצל אורטל (האם)' if r.get('parent') == 'אם' else str(r.get('parent','')),
                      str(r.get('notes',''))])
    def col_name(n):
        result = ''
        while n:
            n, rem = divmod(n-1,26)
            result = chr(65+rem)+result
        return result
    cells=[]
    for ri, record in enumerate(table,1):
        row=[]
        for ci, value in enumerate(record,1):
            ref=f'{col_name(ci)}{ri}'
            value=escape(value, {'"':'&quot;'})
            row.append(f'<c r="{ref}" s="{1 if ri==1 else 2}" t="inlineStr"><is><t xml:space="preserve">{value}</t></is></c>')
        cells.append(f'<row r="{ri}" ht="{34 if ri==1 else 54}" customHeight="1">{"".join(row)}</row>')
    sheet=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0" rightToLeft="1"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols><col min="1" max="1" width="23" customWidth="1"/><col min="2" max="2" width="19" customWidth="1"/><col min="3" max="3" width="19" customWidth="1"/><col min="4" max="4" width="25" customWidth="1"/><col min="5" max="5" width="24" customWidth="1"/><col min="6" max="6" width="65" customWidth="1"/></cols><sheetData>{"".join(cells)}</sheetData><autoFilter ref="A1:F{len(table)}"/><pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/></worksheet>'''
    styles='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF245A81"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD8DEE5"/></left><right style="thin"><color rgb="FFD8DEE5"/></right><top style="thin"><color rgb="FFD8DEE5"/></top><bottom style="thin"><color rgb="FFD8DEE5"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="top" wrapText="1"/></xf></cellXfs></styleSheet>'''
    content_types='''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    workbook=f'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="חגים {year}" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    root_rels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in {'[Content_Types].xml':content_types,'_rels/.rels':root_rels,'xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':workbook_rels,'xl/styles.xml':styles,'xl/worksheets/sheet1.xml':sheet}.items():
            z.writestr(name,data.encode('utf-8'))
    return output.getvalue()

def render():
    st.header('📅 חגים והסדרים')
    st.markdown('<style>[data-testid="stSelectbox"],[data-testid="stTextInput"]{direction:rtl;text-align:right}[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label{text-align:right;width:100%}div[data-baseweb="select"],div[data-baseweb="select"]>div,div[data-baseweb="select"] [role="combobox"]{direction:rtl!important;text-align:right!important;justify-content:flex-start!important}div[data-baseweb="popover"] [role="listbox"],ul[role="listbox"],li[role="option"]{direction:rtl!important;text-align:right!important}div[data-baseweb="popover"] li{justify-content:flex-start!important}</style>',unsafe_allow_html=True)
    st.caption('טבלת 2027 מוצגת מתוך קובץ האקסל המקורי ללא שינוי. שנים חדשות הן הצעות שניתנות לעריכה ולאישור.')
    original=read_original()
    requested=st.query_params.get('holiday_year','2027')
    years=[2027,2028,2029,2030,2031,2032]
    year=st.selectbox('שנת תוכנית',years,index=years.index(int(requested)) if requested.isdigit() and int(requested) in years else 0,key='holiday_year')
    plans=load()
    key=str(year)
    if key not in plans:
        if year==2027:
            plans[key]={'revision':1,'status':'draft','approved_revision':None,'approved_rows':None,'sent_revision':None,'approval_token':None,'history':[],'rows':[dict(r) for r in original]}
            save(plans)
        else:
            st.warning(f'טרם נוצרה תוכנית {year}. היא תתבסס על חלוקת 2027 ותהפוך את ההורים לסירוגין. יש לבדוק את התאריכים לפני שליחה.')
            if st.button(f'➕ יצירת טיוטת {year}',type='primary'):
                plans[key]=new_plan(original,year)
                save(plans)
                st.rerun()
            return
    plan=plans[key]
    rows=plan['rows']
    statuses={'draft':'טיוטה','sent':'נשלחה לעיון','approved':'תוכנית מאושרת','changes':'נדרשים תיקונים'}
    st.write(f"**מצב:** {statuses.get(plan['status'],plan['status'])} | **גרסה:** {plan['revision']}")
    st.warning('שינויים נשמרים בקובץ מקומי בשרת Streamlit, ועלולים להיעלם לאחר אתחול או פריסה מחדש. לשמירה קבועה דרוש בסיס נתונים.')
    with st.expander('✏️ עריכת תוכנית החגים',expanded=False):
        st.caption('העריכות נשמרות בעותק התוכנית, ולא משנות את קובץ Excel המקורי. אחרי שינוי יש לשלוח את הגרסה החדשה לרועי.')
        with st.form(f'holiday_edit_{year}',clear_on_submit=False):
            editable=[{'מזהה':r['id'],'חג':r['holiday'],'תאריך':r['date'],'חלק החג':r['part'],'הורה':r['parent'],'הערות':r['notes']} for r in rows]
            edited=st.data_editor(editable,key=f'holiday_editor_{year}_{plan["revision"]}',hide_index=True,use_container_width=True,num_rows='fixed',disabled=['מזהה'],column_config={'חג':st.column_config.TextColumn('חג',width='medium'),'הורה':st.column_config.SelectboxColumn('הורה',options=['אב','אם'],required=True),'תאריך':st.column_config.TextColumn('תאריך YYYY-MM-DD',required=True),'הערות':st.column_config.TextColumn('הערות',width='large')},row_height=90)
            submit=st.form_submit_button('💾 שמירת שינויים',type='primary')
        if submit:
            try:
                records=edited.to_dict('records') if hasattr(edited,'to_dict') else list(edited)
                updated=[]
                for r in records:
                    d=date.fromisoformat(str(r['תאריך']))
                    if r['הורה'] not in ['אב','אם']:raise ValueError('יש לבחור הורה תקין')
                    updated.append({'id':r['מזהה'],'holiday':str(r['חג']),'date':d.isoformat(),'day_label':('' if year!=2027 else next((x.get('day_label','') for x in rows if x['id']==r['מזהה']),'')),'part':str(r['חלק החג']),'parent':r['הורה'],'notes':str(r['הערות'])})
                if updated!=rows:
                    plan['rows']=updated
                    plan['revision']+=1
                    plan['status']='draft'
                    plan['approval_token']=None
                    plan['sent_revision']=None
                    plan.setdefault('history',[]).append({'action':'edit','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
                    plans[key]=plan
                    save(plans)
                    st.session_state['holiday_save_notice']=f'השינויים נשמרו בגרסה {plan["revision"]}. יש לשלוח אותה לרועי לאישור.'
                    st.rerun()
                else:st.info('לא זוהו שינויים.')
            except (ValueError,TypeError) as e:st.error(f'תאריך או הורה לא תקין: {e}')
    if st.session_state.get('holiday_save_notice'):
        st.success(st.session_state.pop('holiday_save_notice'))
    weekdays=['יום שני','יום שלישי','יום רביעי','יום חמישי','יום שישי','יום שבת','יום ראשון']
    # Correct pre-v12 automatically generated drafts without touching edited/approved plans.
    if year!=2027 and plan.get('revision')==1 and plan.get('status')=='draft' and not any(h.get('action')=='edit' for h in plan.get('history',[])):
        corrected=new_plan(original,year)['rows']
        if any(r.get('date')!=c.get('date') for r,c in zip(rows,corrected)) and len(rows)==len(corrected):
            plan['rows']=corrected
            plan['approval_token']=None
            plan['sent_revision']=None
            plan.setdefault('history',[]).append({'action':'automatic_calendar_correction_v12','at':datetime.now().isoformat(timespec='seconds')})
            plans[str(year)]=plan
            save(plans)
            rows=corrected
            st.warning('תאריכי הטיוטה חושבו מחדש לפי הלוח העברי, כולל תיקון אדר ב׳. יש לבדוק את התוכנית לפני שליחה לאישור.')

    search=st.text_input('🔎 חיפוש חג',placeholder='הקלידי שם חג, למשל פורים',key=f'holiday_search_{year}')
    visible_rows=[r for r in rows if not search.strip() or search.strip().casefold() in str(r.get('holiday','')).casefold() or search.strip().casefold() in str(r.get('part','')).casefold()]
    st.caption(f'מוצגות {len(visible_rows)} מתוך {len(rows)} שורות')
    display=[{'חג':r['holiday'],'תאריך':date.fromisoformat(r['date']).strftime('%d/%m/%Y'),'יום':r.get('day_label','') if year==2027 else weekdays[date.fromisoformat(r['date']).weekday()], 'חלק החג':r['part'],'שהות':('אצל רועי' if r['parent']=='אב' else 'אצל אורטל' if r['parent']=='אם' else r['parent']),'הערות':r['notes']} for r in visible_rows]
    # Render in an explicit RTL HTML table: holiday first, date second, notes last.
    # Unlike st.dataframe, browser RTL layout cannot reverse the visible column order.
    headings=['חג','תאריך','יום','חלק החג','שהות','הערות']
    def safe(v):
        return html.escape(str(v if v is not None else '')).replace('\n','<br>')
    head=''.join(f'<th scope="col">{safe(h)}</th>' for h in headings)
    body=''.join('<tr>'+''.join(f'<td>{safe(r.get(h,""))}</td>' for h in headings)+'</tr>' for r in display)
    st.markdown(f"""
    <style>
    .holiday-scroll {{overflow-x:auto;max-width:100%;margin:0.8rem 0 1.2rem}}
    .holiday-table {{direction:rtl;border-collapse:collapse;width:100%;min-width:900px;text-align:right;table-layout:fixed}}
    .holiday-table th,.holiday-table td {{border:1px solid #d8dee5;padding:10px 12px;vertical-align:top;white-space:normal;overflow-wrap:anywhere;word-break:normal}}
    .holiday-table th {{background:#edf2f7;color:#15212d;font-weight:700}}
    .holiday-table tr:nth-child(even) {{background:rgba(130,140,160,.07)}}
    .holiday-table th:nth-child(1) {{width:15%}}
    .holiday-table th:nth-child(2),.holiday-table td:nth-child(2) {{width:17%;min-width:120px;white-space:nowrap;overflow-wrap:normal}}
    .holiday-table th:nth-child(3) {{width:12%}}
    .holiday-table th:nth-child(4) {{width:13%}}
    .holiday-table th:nth-child(5) {{width:13%}}
    .holiday-table th:nth-child(6) {{width:30%}}
    </style>
    <div class="holiday-scroll"><table class="holiday-table" dir="rtl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>
    """,unsafe_allow_html=True)
    if year==2027:
        st.download_button('📎 הורדת קובץ האקסל המקורי ללא שינוי',SOURCE.read_bytes(),file_name='טבלת סידור חגים 2027.xlsx')
    if plan is not None:
        st.subheader('📨 שליחת תוכנית החגים לרועי בוואטסאפ')
        st.caption('הורידי את קובץ Excel המעודכן כפי שמופיע בטבלה, ושלחי אותו לרועי כקובץ מצורף ב-WhatsApp. אין צורך בהרשמה לאפליקציה.')
        st.download_button('📊 הורדת תוכנית החגים המעודכנת באקסל',
            data=export_plan_xlsx(plan['rows'],year,plan['revision']),
            file_name=f'horut_holidays_{year}_v{plan["revision"]}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True, key=f'xlsx_export_{year}_{plan["revision"]}')
        approval_text=f'רועי, מצורף קובץ תוכנית החגים לשנת {year}, גרסה {plan["revision"]}, לעיונך ולאישורך. לאחר שתעבור על כל התוכנית, אנא השב לי כאן: אני מאשר את תוכנית החגים לשנת {year}, גרסה {plan["revision"]}. אם יש תיקונים, כתוב לי לפני האישור.'
        st.link_button('📱 פתיחת WhatsApp לרועי',f'https://wa.me/?text={quote(approval_text,safe="")}',use_container_width=True)
        st.info('חשוב: WhatsApp לא מאפשר לאתר לצרף קובץ Excel אוטומטית דרך הקישור. לחצי תחילה על הורדת האקסל, פתחי את WhatsApp, בחרי את רועי וצרפי את הקובץ שהורדת באמצעות סמל האטב 📎. ההודעה מכילה בקשת אישור קצרה בלבד, לא את כל הטבלה.')
        if st.button('🔄 הכנת גרסה חדשה לשליחה חוזרת',key=f'whatsapp_resend_{year}'):
            plan['revision']+=1
            plan['status']='draft'
            plan['approval_token']=None
            plan['sent_revision']=None
            plan.setdefault('history',[]).append({'action':'prepared_whatsapp_resend','revision':plan['revision'],'at':datetime.now().isoformat(timespec='seconds')})
            save(plans)
            st.rerun()
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
    # WhatsApp approvals arrive as replies in the sender's own WhatsApp chat.
    # This app does not receive WhatsApp messages or verify approval automatically.
