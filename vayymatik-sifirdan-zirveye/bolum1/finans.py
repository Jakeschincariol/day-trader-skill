# SIFIRDAN ZİRVEYE · Bölüm 1 — finansal model (tek kaynak) + otomatik tutarlılık kontrolleri
# Basitleştirmeler: amortisman ve tahakkuk yok; emanet ürünler işletme stoğu sayılmaz; tedarikçiye satılan emanetin bedeli 1 ay vadeli, yıl sonunda tamamı ödenmiş.
import json, os
D = os.path.dirname(os.path.abspath(__file__))
KAYNAK = {'Birikim': 85000, 'Araba satışı': 230000, 'Arkadaş borcu (Kerem)': 180000, 'Aile borcu': 80000}
SERMAYE = 85000 + 230000                       # Emir'in koyduğu öz para
BORC0 = {'Satıcı (Hasan Usta)': 360000, 'Kerem': 180000, 'Aile': 80000}
KULLANIM = {'Devir peşinatı': 300000, 'Güvenlik ve ekipman': 95000, 'Kira (açılış öncesi ay) + depozito': 75000, 'Tadilat ve tabela': 55000, 'Tedarikçi teminatı': 32000, 'Açılış kasası': 18000}
DURAN = 660000 + 95000 + 55000 + 50000 + 32000  # devralınan işletme + ekipman + tadilat + kira depozitosu + teminat
ACILIS_ONCESI_GIDER = 25000                     # açılış öncesi ayın kirası
KIRA, FATURA, GUVENLIK, MUHASEBE = 25000, 3000, 2500, 2000
# aylık: ciro, SMM, reklam/dekor, finansman gideri, vergi, anapara(satıcı), anapara(Kerem)
AY = [(200000, 174000, 0, 0, 0, 0, 0), (250000, 232500, 30000, 0, 0, 0, 0), (240000, 216000, 0, 8000, 0, 0, 0), (250000, 220000, 0, 0, 0, 10000, 0),
      (270000, 221400, 0, 2750, 0, 10000, 0), (300000, 237000, 2500, 2750, 0, 10000, 0), (330000, 254100, 2500, 2750, 0, 10000, 0), (360000, 273600, 2500, 2750, 0, 10000, 0),
      (400000, 300000, 2500, 2750, 0, 15000, 0), (430000, 322500, 2500, 2750, 0, 15000, 0), (470000, 352500, 3750, 2750, 0, 15000, 0), (500000, 396400, 3750, 2750, 50000, 15000, 20000)]
def durum(kasa, ciro, smm, gider, borc, tedarikci, **ek):
    ozk = kasa + DURAN - borc
    return dict(kasa=kasa, ciro=ciro, smm=smm, gider=gider, net=ciro - smm - gider, borc=borc, tedarikci=tedarikci, kullanilabilir=kasa - tedarikci, ozkaynak=ozk, **ek)
ozk0 = SERMAYE - ACILIS_ONCESI_GIDER
an = {'acilis': durum(18000, 0, 0, 0, sum(BORC0.values()), 0)}
an['ilk_satis'] = durum(18000 + 40000, 40000, 35200, 0, 620000 + 35200, 35200, olay='İlk satış: 40.000 TL bilezik', satis=40000, maliyet=35200)
kasa, ciro, smm, gider, kredi, ted = 18000, 0, 0, 0, 620000, 0; aylar = []
for m, (r, c, rek, fin, ver, ap_s, ap_k) in enumerate(AY, 1):
    sabit = KIRA + FATURA + GUVENLIK + MUHASEBE; pos = r // 100; g = sabit + pos + rek + fin + ver
    if m == 2: an['ay2_harcama'] = durum(kasa - rek, ciro, smm, gider + rek, kredi + ted, ted, olay='Işıklı tabela, dekor, reklam: 30.000 TL')
    odeme_ted = ted + (c if m == 12 else 0); yeni_ted = 0 if m == 12 else c
    kasa = kasa + r - odeme_ted - g - ap_s - ap_k; ted = yeni_ted; kredi -= ap_s + ap_k
    ciro += r; smm += c; gider += g
    aylar.append(dict(ay=m, ciro=r, smm=c, brut=r - c, marj=round((r - c) / r * 100, 1), gider=g, net=r - c - g, anapara=ap_s + ap_k, ytd=durum(kasa, ciro, smm, gider, kredi + ted, ted)))
    an[f'ay{m}_sonu'] = durum(kasa, ciro, smm, gider, kredi + ted, ted)
yil = aylar[-1]['ytd']
GIDER_KALEM = {'Kira': 12 * KIRA, 'Elektrik, su, internet': 12 * FATURA, 'Güvenlik ve sigorta': 12 * GUVENLIK, 'Muhasebe': 12 * MUHASEBE, 'POS / kart komisyonu': sum(a[0] // 100 for a in AY),
               'Reklam ve dekor': sum(a[2] for a in AY), 'Finansman (gecikme cezası + faiz)': sum(a[3] for a in AY), 'Vergi': sum(a[4] for a in AY)}
TEKLIF = 2500000; KALAN = {'Satıcı (Hasan Usta)': 360000 - sum(a[5] for a in AY), 'Kerem': 180000 - sum(a[6] for a in AY), 'Aile': 80000}
final = dict(teklif=TEKLIF, kalan_borc=sum(KALAN.values()), kalan_borc_detay=KALAN, kasa=yil['kasa'], ele_gecen=TEKLIF - sum(KALAN.values()) + yil['kasa'], belirsiz_talep=240000)
final['ele_gecen_talep_ile'] = final['ele_gecen'] - final['belirsiz_talep']
yatirimci = dict(tutar=400000, pay=50, degerleme=800000, ozkaynak=an['ay3_sonu']['ozkaynak'], belirsiz_talep=240000)
SIPARIS = dict(fiyat=100000, maliyet=104000)  # 2. ayda sabit fiyatla alınan düğün seti siparişi (2. ay ciro/SMM içinde)
ozet = dict(devir_bedeli=KULLANIM['Devir peşinatı'] + BORC0['Satıcı (Hasan Usta)'], devir_pesinat=KULLANIM['Devir peşinatı'], satici_borcu=BORC0['Satıcı (Hasan Usta)'], satici_ilk_taksit=BORC0['Satıcı (Hasan Usta)'] // 6,
            toplam_kaynak=sum(KAYNAK.values()), oz_para=SERMAYE, borc_kaynak=KAYNAK['Arkadaş borcu (Kerem)'] + KAYNAK['Aile borcu'], acilis_kasasi=KULLANIM['Açılış kasası'], acilis_borcu=sum(BORC0.values()),
            ilk_satis=an['ilk_satis']['satis'], ilk_satis_maliyet=an['ilk_satis']['maliyet'], ilk_satis_brut=an['ilk_satis']['satis'] - an['ilk_satis']['maliyet'], tabela_dekor_reklam=AY[1][2], gecikme_cezasi=AY[2][3],
            siparis_fiyat=SIPARIS['fiyat'], siparis_maliyet=SIPARIS['maliyet'], siparis_zarar=SIPARIS['maliyet'] - SIPARIS['fiyat'], yeni_taksit_4_8=AY[3][5], yeni_taksit_9_12=AY[8][5], aylik_faiz=AY[4][3],
            yil1_anapara=sum(a[5] + a[6] for a in AY), yil1_anapara_satici=sum(a[5] for a in AY), yil1_anapara_kerem=sum(a[6] for a in AY))
out = dict(ozet=ozet, kaynak=KAYNAK, kullanim=KULLANIM, acilis_borcu=BORC0, ozkaynak_acilis=ozk0, anlar=an, aylar=aylar, gider_kalem=GIDER_KALEM, yatirimci=yatirimci, final=final,
           yeniden_odeme=dict(satici='4.–8. ay: 10.000 TL/ay, 9.–12. ay: 15.000 TL/ay; faiz 2.750 TL/ay (5.–12. ay)', satici_ilk_taksit='6 × 60.000 TL/ay', vadesi_gecen_3ay=180000),
           notlar=['Kurgu: kişiler ve işletme hayalidir.', 'Borç almak gelir, anapara ödemek gider değildir; finansman hareketidir.', 'Emanet ürünler Emir’in stoğu değildir; satılınca bedeli tedarikçiye ödenir.', 'Amortisman ve tahakkuklar gösterilmemiştir (sadeleştirilmiş model).'])
# ---------- kontroller ----------
H = []
def ok(c, m): H.append(('✔' if c else '✘') + ' ' + m); assert c, m
ok(sum(KAYNAK.values()) == 575000 == sum(KULLANIM.values()), 'Kaynak = kullanım = 575.000')
ok(sum(BORC0.values()) == 620000 and 300000 + BORC0['Satıcı (Hasan Usta)'] == 660000, 'Açılış borcu 620.000; devir 300.000 + 360.000 = 660.000')
ok(an['acilis']['ozkaynak'] == ozk0 == 290000, 'Açılış özkaynağı = 315.000 öz para − 25.000 açılış öncesi kira = 290.000')
for k, s in an.items():
    ok(s['net'] == s['ciro'] - s['smm'] - s['gider'], f'{k}: net = ciro − SMM − gider')
    ok(s['ozkaynak'] == ozk0 + s['net'], f'{k}: özkaynak = açılış özkaynağı + net kâr (sermaye hareketi yok)')
    ok(s['kasa'] >= 0, f'{k}: kasa negatif değil')
ok((yil['ciro'], yil['smm'], yil['gider'], yil['net']) == (4000000, 3200000, 560000, 240000), 'Yıl: ciro 4.000.000, SMM 3.200.000, gider 560.000, net 240.000')
ok(sum(GIDER_KALEM.values()) == 560000, 'Gider kalemleri toplamı 560.000')
ok(yil['kasa'] == 18000 + 240000 - 130000 == 128000 and sum(a['anapara'] for a in aylar) == 130000, 'Nakit köprüsü: 18.000 + 240.000 − 130.000 = 128.000')
ok(yil['borc'] == 490000 and yil['tedarikci'] == 0, 'Yıl sonu borç 490.000; tedarikçi borcu 0')
ok(an['ay3_sonu']['net'] == -74900 and an['ay3_sonu']['kasa'] == 159100 and an['ay3_sonu']['tedarikci'] == 216000, '3. ay: zarar 74.900, kasa 159.100, tedarikçi 216.000')
ok(an['ay1_sonu']['kasa'] == 183500 and an['ay2_sonu']['ciro'] == 450000, '1. ay kasa 183.500; 2. ay ciro 450.000')
ok(final['ele_gecen'] == 2138000 and final['ele_gecen_talep_ile'] == 1898000, 'Final: 2.500.000 − 490.000 + 128.000 = 2.138.000')
ok(yil['ozkaynak'] == 530000, 'Yıl sonu özkaynak 530.000')
ok((ozet['devir_bedeli'], ozet['toplam_kaynak'], ozet['oz_para'], ozet['borc_kaynak'], ozet['satici_ilk_taksit']) == (660000, 575000, 315000, 260000, 60000), 'Özet: devir 660.000, kaynak 575.000 = 315.000 öz para + 260.000 borç; taksit 60.000')
ok((ozet['yil1_anapara'], ozet['yil1_anapara_satici'], ozet['yil1_anapara_kerem']) == (130000, 110000, 20000) and final['kalan_borc_detay']['Kerem'] == 160000, 'Yıl 1 anapara 130.000 = satıcı 110.000 + Kerem 20.000; Kerem kalan 160.000')
ok(ozet['ilk_satis_brut'] == 4800 and ozet['siparis_zarar'] == 4000 and ozet['gecikme_cezasi'] == 8000, 'İlk satış brüt 4.800; sipariş zararı 4.000; gecikme cezası 8.000')
out['kontroller'] = H
json.dump(out, open(f'{D}/finans.json', 'w'), ensure_ascii=False, indent=1); print('\n'.join(H[:3] + [f'... {len(H)} kontrol geçti'] + H[-8:]))
# aylık tablo (tablolama programında açmak için)
import csv
with open(f'{D}/finans_aylik.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f, delimiter=';'); w.writerow(['Ay', 'Ciro (satış)', 'Satılan ürün maliyeti', 'Brüt kâr', 'Brüt marj %', 'İşletme giderleri', 'Net kâr/zarar', 'Borç anaparası ödemesi (gider değil)', 'Kasa (ay sonu)', 'Tedarikçiye ödenecek', 'Kullanılabilir nakit', 'Toplam borç', 'Özkaynak'])
    for a in aylar: y = an[f"ay{a['ay']}_sonu"]; w.writerow([a['ay'], a['ciro'], a['smm'], a['brut'], str(a['marj']).replace('.', ','), a['gider'], a['net'], a['anapara'], y['kasa'], y['tedarikci'], y['kullanilabilir'], y['borc'], y['ozkaynak']])
    w.writerow(['Yıl', yil['ciro'], yil['smm'], yil['ciro'] - yil['smm'], str(round((yil['ciro'] - yil['smm']) / yil['ciro'] * 100, 1)).replace('.', ','), yil['gider'], yil['net'], sum(a['anapara'] for a in aylar), yil['kasa'], yil['tedarikci'], yil['kullanilabilir'], yil['borc'], yil['ozkaynak']])
