# MEXC OTE Futures Scanner

MEXC USDT perpetual futures markets for BOS/CHoCH, swing structure and OTE (0.70–0.79) setups.

## Özellikler

- MEXC USDT perpetual paritelerini hacme göre tarar.
- 15 dakika ana yapı, 1 saat ve 4 saat yön doğrulaması kullanır.
- Onaylanmış swing high/low, BOS benzeri yapı kırılımı ve OTE giriş bölgesi üretir.
- Giriş, stop, hedef ve tahmini R/R değerini kaydeder.
- Telegram'a sinyal gönderebilir.
- GitHub Pages üzerinde Türkçe performans paneli sunar.
- Emir açmaz; yalnızca sinyal ve araştırma aracıdır.

## Kurulum

1. Repository > Settings > Secrets and variables > Actions bölümünü aç.
2. `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` adlarında iki repository secret ekle.
3. Actions > MEXC Futures Scan > Run workflow ile ilk taramayı başlat.
4. Settings > Pages > Source bölümünden **GitHub Actions** seç.
5. Actions > Deploy dashboard > Run workflow ile paneli yayınla.

Panel adresi yayın sonrası: https://oznens.github.io/Tgmagic/

## Ayarlar

`config.json` içinden tarama periyodu, en düşük hacim, taranacak parite sayısı, pivot genişliği ve OTE yakınlık eşiği değiştirilebilir.

GitHub Actions zamanlayıcısı yaklaşık beş dakikada bir tetiklenir; GitHub yoğunluğuna bağlı gecikme olabilir. Sinyaller mum kapanışlarına dayanır ve geçmiş swing noktaları sağ taraftan onaylandığı için anlık tepe/dip tahmini yapmaz.

## Uyarı

Bu proje finansal tavsiye değildir. Gerçek para kullanmadan önce uzun dönem geçmiş veri ve ileri test yapılmalıdır.
