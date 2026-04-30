import { useState, useEffect, useCallback } from 'react';
import { Card, Select, Pagination, Empty, Tag, Button } from 'antd';
import { PictureOutlined, DownloadOutlined } from '@ant-design/icons';
import API, { canBrowseData } from '../api';

const placeholderSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='200'%3E%3Crect fill='%23eee' width='260' height='200'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23999'%3ENo Image%3C/text%3E%3C/svg%3E";

export default function AdLibrary() {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [mediaType, setMediaType] = useState('');

  const load = useCallback(async (p, mt) => {
    if (!canBrowseData()) return;
    const pg = p || page;
    const type = mt ?? mediaType;
    const data = await API.get(`/api/ad-library?page=${pg}&media_type=${type}`);
    if (data.success) {
      setItems(data.data);
      setTotal(data.total);
      setPages(data.pages);
    }
  }, [page, mediaType]);

  useEffect(() => { load(1); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onFilterChange = (val) => {
    setMediaType(val);
    setPage(1);
    load(1, val);
  };

  const onPageChange = (p) => {
    setPage(p);
    load(p);
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h4 style={{ margin: 0 }}><PictureOutlined style={{ marginRight: 8 }} />广告素材库</h4>
        <Select value={mediaType} onChange={onFilterChange} style={{ width: 140 }}>
          <Select.Option value="">全部类型</Select.Option>
          <Select.Option value="IMAGE">图片</Select.Option>
          <Select.Option value="VIDEO">视频</Select.Option>
        </Select>
      </div>

      {items.length === 0 ? (
        <Empty description="暂无素材数据。请在 Facebook 广告素材库页面浏览以采集数据。" />
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 16,
          }}>
            {items.map(item => {
              const isVideo = item.media_type === 'VIDEO';
              const mediaUrl = isVideo ? (item.video_hd_url || '') : (item.original_image_url || '');
              const startDate = item.start_date ? new Date(item.start_date).toLocaleDateString() : '';

              return (
                <Card
                  key={item.ad_archive_id}
                  bodyStyle={{ padding: 8 }}
                  cover={
                    isVideo
                      ? <video src={mediaUrl} muted preload="metadata" style={{ width: '100%', height: 200, objectFit: 'cover' }} onMouseOver={e => e.target.play()} onMouseOut={e => e.target.pause()} />
                      : <img alt={item.ad_archive_id} src={mediaUrl || placeholderSvg} style={{ width: '100%', height: 200, objectFit: 'cover' }} onError={e => { e.target.src = placeholderSvg; }} loading="lazy" />
                  }
                  style={{ borderRadius: 10, overflow: 'hidden' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 12, color: '#999' }}>{item.ad_archive_id}</span>
                    <Tag color={isVideo ? 'cyan' : 'blue'}>{item.media_type || 'N/A'}</Tag>
                  </div>
                  {startDate && <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{startDate}</div>}
                  {mediaUrl && (
                    <Button type="primary" ghost size="small" block style={{ marginTop: 8 }} icon={<DownloadOutlined />} href={mediaUrl} target="_blank">
                      下载
                    </Button>
                  )}
                </Card>
              );
            })}
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
            <Pagination current={page} total={total} pageSize={20} onChange={onPageChange} showSizeChanger={false} />
          </div>
        </>
      )}
    </>
  );
}
