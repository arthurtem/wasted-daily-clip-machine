import { readFile } from 'node:fs/promises';
import { del, put } from '@vercel/blob';

const [, , command, ...args] = process.argv;

// Infer the content type so Vercel serves Shorts and thumbnails correctly.
function contentTypeFor(pathname) {
  if (pathname.endsWith('.mp4')) {
    return 'video/mp4';
  }
  if (pathname.endsWith('.jpg') || pathname.endsWith('.jpeg')) {
    return 'image/jpeg';
  }
  return undefined;
}

try {
  if (command === 'put') {
    const [localPath, pathname] = args;
    if (!localPath || !pathname) {
      throw new Error('usage: blob.mjs put <local-path> <pathname>');
    }
    const body = await readFile(localPath);
    const options = {
      access: 'public',
      addRandomSuffix: false,
      allowOverwrite: true,
    };
    const contentType = contentTypeFor(pathname);
    if (contentType) {
      options.contentType = contentType;
    }
    const blob = await put(pathname, body, options);
    console.log(blob.url);
  } else if (command === 'delete') {
    const [url] = args;
    if (!url) {
      throw new Error('usage: blob.mjs delete <url>');
    }
    await del(url);
    console.log('deleted');
  } else {
    throw new Error(`unknown command: ${command ?? '(none)'}`);
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
