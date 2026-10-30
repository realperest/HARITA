# Stil: Koyu teknik

> Bu dosya karakteri tarif eder (renk, font, şekil dili, his). Boyutlar, boşluklar, sütun sayıları ve bileşen ölçüleri sabit değildir; projenin özelliklerine ve çalıştığı ekrana göre belirlenir.

## Ruh hali
Keskin, yoğun, veri odaklı. Koyu zemin, ince çizgiler, sayılarda monospace. Bir gözlem paneli gibi, her piksel iş görür.

## Uygun projeler
Yönetim paneli, izleme ve log ekranları, geliştirici araçları, sıra ve kuyruk sistemleri.

## Renk
| Token | `:root` (varsayılan) | `data-theme=light` |
|---|---|---|
| --zemin | #0E1116 | #F6F8FA |
| --yuzey | #161B22 | #FFFFFF |
| --metin | #E6EDF3 | #1F2328 |
| --metin-ikincil | #8B949E | #59636E |
| --vurgu | #3FB950 | #1A7F37 |
| --vurgu-metin | #0E1116 | #FFFFFF |
| --ikincil | #58A6FF | #0969DA |
| --sinir | #2A313C | #D0D7DE |
| --basari | #3FB950 | - |
| --uyari | #D29922 | - |
| --hata | #F85149 | - |

## Tipografi
- Gövde IBM Plex Sans
- Sayı, kod ve kimlikler JetBrains Mono, sabit genişlikli rakamlar (`tabular-nums`)
- Başlıklar küçük ve orta ağırlıklı

## Şekil dili
- Az yuvarlak köşeler, gölge yok, ince kenarlıklar
- Sıkı, yoğun boşluk

## Bileşenlerin hissi
- Ana eylem vurgu renginde, ikincil eylem ince kenarlıklı ve saydam
- Durum rozeti küçük nokta + metin (dolu blok değil)
- Tabloda sabit başlık, satır üstüne gelince hafif ton
- Komut/arama kutusu monospace ve klavye kısayollu

## Düzen
- Dar yan menü, ince üst araç çubuğu
- Veri ilk ekranda görünür; büyük hero yok
- Küçük ekranda menü çekmeceye döner

## Yasaklar
- Gradyan, parlama, neon
- Büyük boş hero alanı
- Büyük yuvarlak kartlar ve pastel renkler

## CSS değişkenleri
```css
:root {
  --zemin: #0E1116;
  --yuzey: #161B22;
  --metin: #E6EDF3;
  --metin-ikincil: #8B949E;
  --vurgu: #3FB950;
  --vurgu-metin: #0E1116;
  --ikincil: #58A6FF;
  --sinir: #2A313C;
  --basari: #3FB950;
  --uyari: #D29922;
  --hata: #F85149;
  --font-baslik: "IBM Plex Sans", "Segoe UI", sans-serif;
  --font-govde: "IBM Plex Sans", "Segoe UI", sans-serif;
  --font-sayi: "JetBrains Mono", Consolas, monospace;
  --radius-buton: 6px;
  --radius-kart: 6px;
  --radius-alan: 6px;
  --golge-kart: none;
}
:root[data-theme="light"] {
  --zemin: #F6F8FA;
  --yuzey: #FFFFFF;
  --metin: #1F2328;
  --metin-ikincil: #59636E;
  --vurgu: #1A7F37;
  --vurgu-metin: #FFFFFF;
  --ikincil: #0969DA;
  --sinir: #D0D7DE;
}
```
